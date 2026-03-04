"""
Supplier management routes.

  GET  /suppliers              — list all suppliers
  GET  /suppliers/new          — create form
  POST /suppliers/new          — save new supplier
  GET  /suppliers/{id}         — detail + linked products + purchase history
  GET  /suppliers/{id}/edit    — edit form
  POST /suppliers/{id}/edit    — save edits
  POST /suppliers/{id}/delete  — soft-delete
  GET  /suppliers/reorder      — reorder suggestions (products at/below threshold)
  POST /suppliers/reorder/order — create a draft purchase transaction per supplier
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth

router    = APIRouter(prefix="/suppliers")
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
async def suppliers_list(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red:
        return red
    suppliers = db.query(models.Supplier).filter(
        models.Supplier.shop_id == shop.id,
        models.Supplier.is_active == True,
    ).order_by(models.Supplier.name).all()
    return templates.TemplateResponse("suppliers/index.html", {
        "request": request, "shop": shop, "suppliers": suppliers,
    })


# ── Create ────────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def supplier_new_form(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    return templates.TemplateResponse("suppliers/form.html", {
        "request": request, "shop": shop, "supplier": None,
    })


@router.post("/new", response_class=HTMLResponse)
async def supplier_create(
    request: Request,
    name:           str   = Form(...),
    contact_name:   str   = Form(default=""),
    phone:          str   = Form(default=""),
    email:          str   = Form(default=""),
    website:        str   = Form(default=""),
    notes:          str   = Form(default=""),
    lead_time_days: int   = Form(default=3),
    db: Session = Depends(get_db),
):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    s = models.Supplier(
        shop_id=shop.id, name=name.strip(),
        contact_name=contact_name.strip() or None,
        phone=phone.strip() or None,
        email=email.strip() or None,
        website=website.strip() or None,
        notes=notes.strip() or None,
        lead_time_days=max(0, lead_time_days),
    )
    db.add(s); db.commit()
    return RedirectResponse(url=f"/suppliers/{s.id}", status_code=302)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{supplier_id}", response_class=HTMLResponse)
async def supplier_detail(request: Request, supplier_id: int,
                          db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    supplier = _get_or_404(supplier_id, shop.id, db)
    if not supplier:
        return RedirectResponse(url="/suppliers", status_code=302)

    # Products using this supplier
    products = db.query(models.Product).filter(
        models.Product.supplier_id == supplier_id,
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
    ).order_by(models.Product.name).all()

    # Recent purchases from this supplier
    recent_txns = db.query(models.Transaction).filter(
        models.Transaction.supplier_id == supplier_id,
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.PURCHASE,
    ).order_by(models.Transaction.created_at.desc()).limit(10).all()

    return templates.TemplateResponse("suppliers/detail.html", {
        "request": request, "shop": shop, "supplier": supplier,
        "products": products, "recent_txns": recent_txns,
    })


# ── Edit ──────────────────────────────────────────────────────────────────────

@router.get("/{supplier_id}/edit", response_class=HTMLResponse)
async def supplier_edit_form(request: Request, supplier_id: int,
                             db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    supplier = _get_or_404(supplier_id, shop.id, db)
    if not supplier:
        return RedirectResponse(url="/suppliers", status_code=302)
    return templates.TemplateResponse("suppliers/form.html", {
        "request": request, "shop": shop, "supplier": supplier,
    })


@router.post("/{supplier_id}/edit", response_class=HTMLResponse)
async def supplier_update(
    request: Request, supplier_id: int,
    name:           str = Form(...),
    contact_name:   str = Form(default=""),
    phone:          str = Form(default=""),
    email:          str = Form(default=""),
    website:        str = Form(default=""),
    notes:          str = Form(default=""),
    lead_time_days: int = Form(default=3),
    db: Session = Depends(get_db),
):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    supplier = _get_or_404(supplier_id, shop.id, db)
    if not supplier:
        return RedirectResponse(url="/suppliers", status_code=302)
    supplier.name          = name.strip()
    supplier.contact_name  = contact_name.strip() or None
    supplier.phone         = phone.strip() or None
    supplier.email         = email.strip() or None
    supplier.website       = website.strip() or None
    supplier.notes         = notes.strip() or None
    supplier.lead_time_days = max(0, lead_time_days)
    db.commit()
    return RedirectResponse(url=f"/suppliers/{supplier_id}", status_code=302)


@router.post("/{supplier_id}/delete")
async def supplier_delete(request: Request, supplier_id: int,
                          db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red
    supplier = _get_or_404(supplier_id, shop.id, db)
    if supplier:
        supplier.is_active = False
        db.commit()
    return RedirectResponse(url="/suppliers", status_code=302)


# ── Reorder suggestions ───────────────────────────────────────────────────────

@router.get("/reorder/suggestions", response_class=HTMLResponse)
async def reorder_suggestions(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    red  = _require_manager(request, shop)
    if red: return red

    low = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
        models.Product.stock_quantity <= models.Product.low_stock_threshold,
    ).order_by(models.Product.name).all()

    # Group by supplier
    by_supplier: dict = {}
    no_supplier = []
    for p in low:
        if p.supplier:
            sid = p.supplier_id
            if sid not in by_supplier:
                by_supplier[sid] = {"supplier": p.supplier, "products": []}
            by_supplier[sid]["products"].append(p)
        else:
            no_supplier.append(p)

    return templates.TemplateResponse("suppliers/reorder.html", {
        "request": request, "shop": shop,
        "by_supplier": list(by_supplier.values()),
        "no_supplier": no_supplier,
        "total_low": len(low),
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(supplier_id: int, shop_id: int, db: Session):
    return db.query(models.Supplier).filter(
        models.Supplier.id == supplier_id,
        models.Supplier.shop_id == shop_id,
        models.Supplier.is_active == True,
    ).first()
