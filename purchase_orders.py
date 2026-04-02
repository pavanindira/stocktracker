"""
Purchase Order routes.

  GET  /purchase-orders              — list POs
  GET  /purchase-orders/new          — create form
  POST /purchase-orders/new          — save draft PO
  GET  /purchase-orders/{id}         — detail view
  GET  /purchase-orders/{id}/edit    — edit form (draft only)
  POST /purchase-orders/{id}/edit    — save edits
  POST /purchase-orders/{id}/send    — mark as sent (draft → sent)
  GET  /purchase-orders/{id}/receive — receive-delivery form
  POST /purchase-orders/{id}/receive — record received quantities → purchase transactions
  POST /purchase-orders/{id}/cancel  — cancel
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth, fefo
from audit import log_action
from datetime import datetime, timezone

router    = APIRouter(prefix="/purchase-orders")
templates = Jinja2Templates(directory="templates")


def _shop(request, db):
    sid = request.session.get("shop_id")
    return db.query(models.Shop).filter(models.Shop.id == sid).first() if sid else None


def _guard(request, shop):
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return None


def _get_po(po_id, shop_id, db):
    return db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.id == po_id,
        models.PurchaseOrder.shop_id == shop_id,
    ).first()


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def po_list(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    pos = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.shop_id == shop.id,
    ).order_by(models.PurchaseOrder.created_at.desc()).all()
    return templates.TemplateResponse("purchase_orders/index.html", {
        "request": request, "shop": shop, "pos": pos,
    })


# ── Create ────────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def po_new_form(request: Request, supplier_id: str = "",
                      db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    suppliers = db.query(models.Supplier).filter(
        models.Supplier.shop_id == shop.id,
        models.Supplier.is_active == True,
    ).order_by(models.Supplier.name).all()
    products = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
    ).order_by(models.Product.name).all()
    # Pre-fill with low-stock products for the selected supplier
    prefill = []
    if supplier_id and supplier_id.isdigit():
        prefill = [p for p in products
                   if p.supplier_id == int(supplier_id) and p.is_low_stock]
    return templates.TemplateResponse("purchase_orders/form.html", {
        "request": request, "shop": shop, "po": None,
        "suppliers": suppliers, "products": products,
        "prefill": prefill,
        "selected_supplier_id": int(supplier_id) if supplier_id.isdigit() else None,
    })


@router.post("/new", response_class=HTMLResponse)
async def po_create(request: Request, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    form = await request.form()

    supplier_id       = form.get("supplier_id") or None
    reference         = form.get("reference", "").strip() or None
    notes             = form.get("notes", "").strip() or None
    expected_delivery = _parse_date(form.get("expected_delivery", ""))

    po = models.PurchaseOrder(
        shop_id=shop.id,
        supplier_id=int(supplier_id) if supplier_id else None,
        reference=reference,
        notes=notes,
        expected_delivery=expected_delivery,
        status=models.POStatus.DRAFT,
    )
    db.add(po); db.flush()

    product_ids = form.getlist("product_id[]")
    quantities  = form.getlist("quantity[]")
    unit_prices = form.getlist("unit_price[]")
    total = 0.0
    for pid, qty, price in zip(product_ids, quantities, unit_prices):
        if not pid or not qty: continue
        try:
            qty_f   = float(qty)
            price_f = float(price or 0)
        except ValueError:
            continue
        if qty_f <= 0: continue
        db.add(models.PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=int(pid),
            quantity_ordered=qty_f,
            unit_price=price_f,
        ))
        total += qty_f * price_f

    po.total_amount = round(total, 2)
    log_action(db, shop.id, request, "CREATE_PO", "purchase_order", po.id,
               f"Created PO #{po.id} with {len(product_ids)} line items")
    db.commit()
    return RedirectResponse(url=f"/purchase-orders/{po.id}", status_code=302)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{po_id}", response_class=HTMLResponse)
async def po_detail(request: Request, po_id: int, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    po = _get_po(po_id, shop.id, db)
    if not po: return RedirectResponse(url="/purchase-orders", status_code=302)
    return templates.TemplateResponse("purchase_orders/detail.html", {
        "request": request, "shop": shop, "po": po,
    })


# ── Edit ──────────────────────────────────────────────────────────────────────

@router.get("/{po_id}/edit", response_class=HTMLResponse)
async def po_edit_form(request: Request, po_id: int, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    po = _get_po(po_id, shop.id, db)
    if not po or po.status != models.POStatus.DRAFT:
        return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=302)
    suppliers = db.query(models.Supplier).filter(
        models.Supplier.shop_id == shop.id, models.Supplier.is_active == True
    ).order_by(models.Supplier.name).all()
    products = db.query(models.Product).filter(
        models.Product.shop_id == shop.id, models.Product.is_active == True
    ).order_by(models.Product.name).all()
    return templates.TemplateResponse("purchase_orders/form.html", {
        "request": request, "shop": shop, "po": po,
        "suppliers": suppliers, "products": products, "prefill": [],
        "selected_supplier_id": po.supplier_id,
    })


@router.post("/{po_id}/edit", response_class=HTMLResponse)
async def po_update(request: Request, po_id: int, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    po = _get_po(po_id, shop.id, db)
    if not po or po.status != models.POStatus.DRAFT:
        return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=302)
    form = await request.form()
    try:
        po.supplier_id = int(form.get("supplier_id")) if form.get("supplier_id") else None
    except ValueError:
        pass  # Keep as None if invalid
    po.reference         = form.get("reference", "").strip() or None
    po.notes             = form.get("notes", "").strip() or None
    po.expected_delivery = _parse_date(form.get("expected_delivery", ""))

    # Replace items
    for item in po.items: db.delete(item)
    db.flush()

    product_ids = form.getlist("product_id[]")
    quantities  = form.getlist("quantity[]")
    unit_prices = form.getlist("unit_price[]")
    total = 0.0
    for pid, qty, price in zip(product_ids, quantities, unit_prices):
        if not pid or not qty: continue
        try:
            qty_f = float(qty); price_f = float(price or 0)
        except ValueError: continue
        if qty_f <= 0: continue
        db.add(models.PurchaseOrderItem(
            purchase_order_id=po.id, product_id=int(pid),
            quantity_ordered=qty_f, unit_price=price_f,
        ))
        total += qty_f * price_f
    po.total_amount = round(total, 2)
    log_action(db, shop.id, request, "EDIT_PO", "purchase_order", po.id, f"Edited PO #{po.id}")
    db.commit()
    return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=302)


# ── Mark sent ─────────────────────────────────────────────────────────────────

@router.post("/{po_id}/send")
async def po_send(request: Request, po_id: int, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    po = _get_po(po_id, shop.id, db)
    if po and po.status == models.POStatus.DRAFT:
        po.status  = models.POStatus.SENT
        po.sent_at = datetime.now(timezone.utc)
        log_action(db, shop.id, request, "SEND_PO", "purchase_order", po.id, f"Marked PO #{po.id} as sent")
        db.commit()
    return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=302)


# ── Receive delivery ──────────────────────────────────────────────────────────

@router.get("/{po_id}/receive", response_class=HTMLResponse)
async def po_receive_form(request: Request, po_id: int, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    po = _get_po(po_id, shop.id, db)
    if not po or po.status not in (models.POStatus.SENT, models.POStatus.PARTIALLY_RECEIVED):
        return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=302)
    return templates.TemplateResponse("purchase_orders/receive.html", {
        "request": request, "shop": shop, "po": po,
    })


@router.post("/{po_id}/receive", response_class=HTMLResponse)
async def po_receive(request: Request, po_id: int, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    po = _get_po(po_id, shop.id, db)
    if not po or po.status not in (models.POStatus.SENT, models.POStatus.PARTIALLY_RECEIVED):
        return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=302)
    form = await request.form()

    # Build one purchase transaction for this receipt
    txn = models.Transaction(
        shop_id=shop.id,
        supplier_id=po.supplier_id,
        transaction_type=models.TransactionType.PURCHASE,
        reference=f"PO-{po.id}",
        notes=f"Received against PO #{po.id}",
        total_amount=0.0,
        tax_amount=0.0, tax_rate=0.0,
    )
    db.add(txn); db.flush()

    total = 0.0
    any_received = False
    for item in po.items:
        qty_key = f"received_{item.id}"
        exp_key = f"expiry_{item.id}"
        lot_key = f"lot_{item.id}"
        qty_s   = form.get(qty_key, "0")
        try:
            qty = float(qty_s)
        except ValueError:
            qty = 0.0
        if qty <= 0: continue

        any_received = True
        expiry  = _parse_date(form.get(exp_key, ""))
        lot     = form.get(lot_key, "").strip() or None

        # Create stock batch
        fefo.create_batch(item.product, qty,
                          expiry_date=expiry or item.expiry_date or item.product.default_expiry_date,
                          lot_number=lot, db=db)

        # Update PO item received qty
        item.quantity_received = round(item.quantity_received + qty, 4)

        sub = round(qty * item.unit_price, 2)
        total += sub
        db.add(models.TransactionItem(
            transaction_id=txn.id,
            product_id=item.product_id,
            quantity=qty,
            unit_price=item.unit_price,
            subtotal=sub,
            lot_number=lot,
        ))

    if not any_received:
        db.rollback()
        return RedirectResponse(url=f"/purchase-orders/{po_id}/receive", status_code=302)

    txn.total_amount = round(total, 2)

    # Update PO status
    if po.items_received:
        po.status       = models.POStatus.COMPLETED
        po.completed_at = datetime.now(timezone.utc)
    else:
        po.status = models.POStatus.PARTIALLY_RECEIVED

    log_action(db, shop.id, request, "RECEIVE_PO", "purchase_order", po.id,
               f"Received delivery against PO #{po.id}, created transaction #{txn.id}")
    db.commit()
    return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=302)


# ── Cancel ────────────────────────────────────────────────────────────────────

@router.post("/{po_id}/cancel")
async def po_cancel(request: Request, po_id: int, db: Session = Depends(get_db)):
    shop = _shop(request, db)
    if red := _guard(request, shop): return red
    po = _get_po(po_id, shop.id, db)
    if po and po.status not in (models.POStatus.COMPLETED, models.POStatus.CANCELLED):
        po.status = models.POStatus.CANCELLED
        log_action(db, shop.id, request, "CANCEL_PO", "purchase_order", po.id, f"Cancelled PO #{po.id}")
        db.commit()
    return RedirectResponse(url="/purchase-orders", status_code=302)
