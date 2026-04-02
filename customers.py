"""
Customer management routes.

  GET  /customers          — list customers
  GET  /customers/new      — create form
  POST /customers/new      — save
  GET  /customers/{id}     — detail + transaction history
  GET  /customers/{id}/edit
  POST /customers/{id}/edit
  POST /customers/{id}/delete
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth
from audit import log_action

router    = APIRouter(prefix="/customers")
templates = Jinja2Templates(directory="templates")


def _shop(request, db):
    sid = request.session.get("shop_id")
    return db.query(models.Shop).filter(models.Shop.id == sid).first() if sid else None


def _guard(request, shop, role="cashier"):
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, role):
        return RedirectResponse(url="/dashboard", status_code=302)
    return None


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def customer_list(request: Request, search: str = "",
                        db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    q = db.query(models.Customer).filter(
        models.Customer.shop_id == shop.id,
        models.Customer.is_active == True,
    )
    if search:
        # Escape LIKE wildcards in search term
        def _escape_like(s):
            return (s.replace('%', r'\%').replace('_', r'\_')) if s else ''
        esc = _escape_like(search)
        q = q.filter(
            models.Customer.name.ilike(f"%{esc}%", escape='\\') |
            models.Customer.phone.ilike(f"%{esc}%", escape='\\') |
            models.Customer.email.ilike(f"%{esc}%", escape='\\')
        )
    customers = q.order_by(models.Customer.name).all()
    return templates.TemplateResponse("customers/index.html", {
        "request": request, "shop": shop,
        "customers": customers, "search": search,
    })


# ── Create ────────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def customer_new_form(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    return templates.TemplateResponse("customers/form.html", {
        "request": request, "shop": shop, "customer": None,
    })


@router.post("/new", response_class=HTMLResponse)
async def customer_create(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    form = await request.form()
    c = models.Customer(
        shop_id=shop.id,
        name=form.get("name", "").strip(),
        phone=form.get("phone", "").strip() or None,
        email=form.get("email", "").strip() or None,
        notes=form.get("notes", "").strip() or None,
    )
    db.add(c); db.flush()
    log_action(db, shop.id, request, "CREATE_CUSTOMER", "customer", c.id, f"Created customer: {c.name}")
    db.commit()
    return RedirectResponse(url=f"/customers/{c.id}", status_code=302)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}", response_class=HTMLResponse)
async def customer_detail(request: Request, customer_id: int,
                          db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    c = _get(customer_id, shop.id, db)
    if not c: return RedirectResponse(url="/customers", status_code=302)
    txns = db.query(models.Transaction).filter(
        models.Transaction.customer_id == customer_id,
        models.Transaction.shop_id == shop.id,
    ).order_by(models.Transaction.created_at.desc()).limit(20).all()
    return templates.TemplateResponse("customers/detail.html", {
        "request": request, "shop": shop, "customer": c, "transactions": txns,
    })


# ── Edit ──────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}/edit", response_class=HTMLResponse)
async def customer_edit_form(request: Request, customer_id: int,
                             db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    c = _get(customer_id, shop.id, db)
    if not c: return RedirectResponse(url="/customers", status_code=302)
    return templates.TemplateResponse("customers/form.html", {
        "request": request, "shop": shop, "customer": c,
    })


@router.post("/{customer_id}/edit", response_class=HTMLResponse)
async def customer_update(request: Request, customer_id: int,
                          db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    c = _get(customer_id, shop.id, db)
    if not c: return RedirectResponse(url="/customers", status_code=302)
    form = await request.form()
    c.name  = form.get("name", "").strip()
    c.phone = form.get("phone", "").strip() or None
    c.email = form.get("email", "").strip() or None
    c.notes = form.get("notes", "").strip() or None
    log_action(db, shop.id, request, "EDIT_CUSTOMER", "customer", c.id, f"Edited customer: {c.name}")
    db.commit()
    return RedirectResponse(url=f"/customers/{customer_id}", status_code=302)


@router.post("/{customer_id}/delete")
async def customer_delete(request: Request, customer_id: int,
                          db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop, "manager"): return red
    c = _get(customer_id, shop.id, db)
    if c:
        c.is_active = False
        log_action(db, shop.id, request, "DELETE_CUSTOMER", "customer", c.id, f"Removed customer: {c.name}")
        db.commit()
    return RedirectResponse(url="/customers", status_code=302)


def _get(customer_id, shop_id, db):
    return db.query(models.Customer).filter(
        models.Customer.id == customer_id,
        models.Customer.shop_id == shop_id,
        models.Customer.is_active == True,
    ).first()
