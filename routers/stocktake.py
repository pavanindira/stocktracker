"""
Stocktake (physical count) routes.

  GET  /stocktake                       — list stocktakes
  GET  /stocktake/new                   — create form
  POST /stocktake/new                   — save, snapshot all product qtys
  GET  /stocktake/{id}                  — count entry screen
  POST /stocktake/{id}/count            — save counted quantities (AJAX or form)
  GET  /stocktake/{id}/review           — review variances before commit
  POST /stocktake/{id}/commit           — write adjustment transactions, mark complete
  POST /stocktake/{id}/delete           — delete draft stocktake
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from database import get_db
import models, auth
from datetime import datetime, timezone

router    = APIRouter(prefix="/stocktake")
templates = Jinja2Templates(directory="templates")


def _shop(request: Request, db: Session):
    sid = request.session.get("shop_id")
    if not sid:
        return None
    return db.query(models.Shop).filter(models.Shop.id == sid).first()


def _require_manager(request, shop):
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return None


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def stocktake_list(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    stocktakes = db.query(models.Stocktake).filter(
        models.Stocktake.shop_id == shop.id,
    ).order_by(models.Stocktake.created_at.desc()).all()
    return templates.TemplateResponse("stocktake/index.html", {
        "request": request, "shop": shop, "stocktakes": stocktakes,
    })


# ── Create ────────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def stocktake_new_form(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    categories = db.query(models.Category).filter(
        models.Category.shop_id == shop.id).order_by(models.Category.name).all()
    product_count = db.query(func.count(models.Product.id)).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
    ).scalar()
    return templates.TemplateResponse("stocktake/new.html", {
        "request": request, "shop": shop,
        "categories": categories, "product_count": product_count,
    })


@router.post("/new", response_class=HTMLResponse)
async def stocktake_create(
    request: Request,
    name:        str = Form(...),
    notes:       str = Form(default=""),
    category_id: str = Form(default=""),
    db: Session = Depends(get_db),
):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red

    st = models.Stocktake(
        shop_id=shop.id,
        name=name.strip(),
        notes=notes.strip() or None,
        status=models.StocktakeStatus.IN_PROGRESS,
    )
    db.add(st)
    db.flush()

    # Snapshot all active products (optionally filtered by category)
    q = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
    )
    if category_id and category_id.isdigit():
        q = q.filter(models.Product.category_id == int(category_id))
    products = q.order_by(models.Product.name).all()

    for p in products:
        db.add(models.StocktakeItem(
            stocktake_id=st.id,
            product_id=p.id,
            system_quantity=p.stock_quantity,
            counted_quantity=None,
        ))

    db.commit()
    return RedirectResponse(url=f"/stocktake/{st.id}", status_code=302)


# ── Count entry ───────────────────────────────────────────────────────────────

@router.get("/{stocktake_id}", response_class=HTMLResponse)
async def stocktake_count(request: Request, stocktake_id: int,
                          db: Session = Depends(get_db),
                          search: str = "", filter: str = "all"):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    st = _get_st(stocktake_id, shop.id, db)
    if not st:
        return RedirectResponse(url="/stocktake", status_code=302)

    items = st.items
    if search:
        items = [i for i in items
                 if search.lower() in i.product.name.lower()
                 or (i.product.sku and search.lower() in i.product.sku.lower())]
    if filter == "uncounted":
        items = [i for i in items if i.counted_quantity is None]
    elif filter == "variance":
        items = [i for i in items if i.counted_quantity is not None and i.variance != 0]
    elif filter == "ok":
        items = [i for i in items if i.counted_quantity is not None and i.variance == 0]

    return templates.TemplateResponse("stocktake/count.html", {
        "request": request, "shop": shop, "st": st, "items": items,
        "search": search, "filter": filter,
        "total": st.total_items, "counted": st.items_counted,
        "variances": st.variance_count,
    })


# ── Save a single count (AJAX) ────────────────────────────────────────────────

@router.post("/{stocktake_id}/count/{item_id}", response_class=JSONResponse)
async def save_count(
    request: Request, stocktake_id: int, item_id: int,
    db: Session = Depends(get_db),
):
    shop = _shop(request, db)
    if not shop:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    st = _get_st(stocktake_id, shop.id, db)
    if not st or st.status == models.StocktakeStatus.COMPLETED:
        return JSONResponse({"error": "stocktake not found or completed"}, status_code=404)

    body = await request.json()
    counted = body.get("counted_quantity")
    notes   = body.get("notes", "")

    item = db.query(models.StocktakeItem).filter(
        models.StocktakeItem.id == item_id,
        models.StocktakeItem.stocktake_id == stocktake_id,
    ).first()
    if not item:
        return JSONResponse({"error": "item not found"}, status_code=404)

    if counted is None or counted == "":
        item.counted_quantity = None
    else:
        item.counted_quantity = float(counted)
    item.notes = str(notes).strip() or None
    db.commit()

    return {
        "id":               item.id,
        "counted_quantity": item.counted_quantity,
        "variance":         item.variance,
        "variance_pct":     item.variance_pct,
        "counted_total":    st.items_counted,
        "total":            st.total_items,
        "variance_count":   st.variance_count,
    }


# ── Review variances ──────────────────────────────────────────────────────────

@router.get("/{stocktake_id}/review", response_class=HTMLResponse)
async def stocktake_review(request: Request, stocktake_id: int,
                           db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    st = _get_st(stocktake_id, shop.id, db)
    if not st:
        return RedirectResponse(url="/stocktake", status_code=302)

    variances = [i for i in st.items if i.counted_quantity is not None and i.variance != 0]
    matched   = [i for i in st.items if i.counted_quantity is not None and i.variance == 0]
    uncounted = [i for i in st.items if i.counted_quantity is None]

    # Value impact: variance * cost_price
    value_impact = sum(i.variance * i.product.cost_price for i in variances)

    return templates.TemplateResponse("stocktake/review.html", {
        "request": request, "shop": shop, "st": st,
        "variances": variances, "matched": matched, "uncounted": uncounted,
        "value_impact": value_impact,
    })


# ── Commit ─────────────────────────────────────────────────────────────────────

@router.post("/{stocktake_id}/commit", response_class=HTMLResponse)
async def stocktake_commit(request: Request, stocktake_id: int,
                           db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    st = _get_st(stocktake_id, shop.id, db)
    if not st or st.status == models.StocktakeStatus.COMPLETED:
        return RedirectResponse(url="/stocktake", status_code=302)

    variances = [i for i in st.items
                 if i.counted_quantity is not None and i.variance != 0]

    if variances:
        # One adjustment transaction per variance item
        total = sum(abs(i.variance) * i.product.cost_price for i in variances)
        txn = models.Transaction(
            shop_id=shop.id,
            transaction_type=models.TransactionType.ADJUSTMENT,
            reference=f"STOCKTAKE-{st.id}",
            notes=f"Stocktake adjustment: {st.name}",
            total_amount=round(total, 2),
            tax_amount=0.0, tax_rate=0.0,
        )
        db.add(txn)
        db.flush()

        for item in variances:
            # Set stock to counted quantity
            item.product.stock_quantity = item.counted_quantity
            db.add(models.TransactionItem(
                transaction_id=txn.id,
                product_id=item.product_id,
                quantity=item.counted_quantity,   # new absolute qty
                unit_price=item.product.cost_price,
                subtotal=round(abs(item.variance) * item.product.cost_price, 2),
            ))

    st.status       = models.StocktakeStatus.COMPLETED
    st.completed_at = datetime.now(timezone.utc)
    db.commit()

    return RedirectResponse(url=f"/stocktake/{stocktake_id}/done", status_code=302)


@router.get("/{stocktake_id}/done", response_class=HTMLResponse)
async def stocktake_done(request: Request, stocktake_id: int,
                         db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    st = _get_st(stocktake_id, shop.id, db)
    if not st:
        return RedirectResponse(url="/stocktake", status_code=302)
    adjusted = [i for i in st.items if i.counted_quantity is not None and i.variance != 0]
    return templates.TemplateResponse("stocktake/done.html", {
        "request": request, "shop": shop, "st": st, "adjusted": adjusted,
    })


# ── Delete (draft only) ───────────────────────────────────────────────────────

@router.post("/{stocktake_id}/delete")
async def stocktake_delete(request: Request, stocktake_id: int,
                           db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    st = _get_st(stocktake_id, shop.id, db)
    if st and st.status != models.StocktakeStatus.COMPLETED:
        db.delete(st)
        db.commit()
    return RedirectResponse(url="/stocktake", status_code=302)


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_st(stocktake_id: int, shop_id: int, db: Session):
    return db.query(models.Stocktake).filter(
        models.Stocktake.id == stocktake_id,
        models.Stocktake.shop_id == shop_id,
    ).first()
