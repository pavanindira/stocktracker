from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from audit import log_action
import models
import json

router = APIRouter(prefix="/transactions")
templates = Jinja2Templates(directory="templates")


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


@router.get("", response_class=HTMLResponse)
async def transactions_list(request: Request, db: Session = Depends(get_db), type: str = ""):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    query = db.query(models.Transaction).filter(models.Transaction.shop_id == shop.id)
    if type in ("sale", "purchase", "adjustment"):
        query = query.filter(models.Transaction.transaction_type == type)

    transactions = query.order_by(models.Transaction.created_at.desc()).limit(100).all()

    return templates.TemplateResponse("transactions/index.html", {
        "request": request, "shop": shop, "transactions": transactions, "filter_type": type
    })


@router.get("/new", response_class=HTMLResponse)
async def transaction_new(request: Request, db: Session = Depends(get_db), type: str = "sale"):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    products = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True
    ).order_by(models.Product.name).all()

    customers = db.query(models.Customer).filter(
        models.Customer.shop_id == shop.id,
        models.Customer.is_active == True
    ).order_by(models.Customer.name).all()

    return templates.TemplateResponse("transactions/form.html", {
        "request": request, "shop": shop, "products": products,
        "transaction_type": type, "error": None, "customers": customers
    })


@router.post("/new", response_class=HTMLResponse)
async def transaction_create(
    request: Request,
    db: Session = Depends(get_db)
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    transaction_type = form.get("transaction_type", "sale")
    reference = form.get("reference", "")
    notes = form.get("notes", "")
    return_of_id = form.get("return_of_id") or None
    customer_id = form.get("customer_id") or None

    # Parse discount and tax fields from form
    discount_type_str = form.get("discount_type", "none")
    discount_value = float(form.get("discount_value", "0") or "0")
    tax_rate = float(form.get("tax_rate", "0") or "0")

    # Parse line-level discount if present
    line_discounts = form.getlist("discount_amount[]")

    # Parse items from form (product_id[], quantity[], unit_price[])
    product_ids = form.getlist("product_id[]")
    quantities = form.getlist("quantity[]")
    unit_prices = form.getlist("unit_price[]")

    if not product_ids:
        products = db.query(models.Product).filter(
            models.Product.shop_id == shop.id, models.Product.is_active == True
        ).order_by(models.Product.name).all()
        return templates.TemplateResponse("transactions/form.html", {
            "request": request, "shop": shop, "products": products,
            "transaction_type": transaction_type, "error": "Please add at least one item."
        })

    subtotal = 0.0
    items_data = []
    for i, (pid, qty, price) in enumerate(zip(product_ids, quantities, unit_prices)):
        try:
            qty_f = float(qty)
            price_f = float(price)
        except ValueError:
            continue
        if qty_f <= 0:
            continue
        product = db.query(models.Product).filter(
            models.Product.id == int(pid), models.Product.shop_id == shop.id
        ).first()
        if not product:
            continue

        # Calculate line-level discount if present
        line_discount = 0.0
        if i < len(line_discounts) and line_discounts[i]:
            try:
                line_discount = float(line_discounts[i])
            except ValueError:
                line_discount = 0.0

        line_subtotal = qty_f * price_f - line_discount
        subtotal += line_subtotal
        items_data.append((product, qty_f, price_f, line_subtotal, line_discount))

    # Calculate discount amount based on discount type
    discount_amount = 0.0
    if discount_type_str == "percentage":
        discount_amount = subtotal * discount_value / 100
    elif discount_type_str == "fixed":
        discount_amount = min(discount_value, subtotal)

    # Calculate discounted subtotal
    discounted_subtotal = subtotal - discount_amount

    # Calculate tax amount on discounted subtotal
    tax_amount = discounted_subtotal * tax_rate / 100

    # Calculate final total amount
    total_amount = discounted_subtotal + tax_amount

    transaction = models.Transaction(
        shop_id=shop.id,
        transaction_type=models.TransactionType(transaction_type),
        reference=reference or None,
        notes=notes or None,
        total_amount=total_amount,
        discount_type=models.DiscountType(discount_type_str),
        discount_value=discount_value,
        discount_amount=discount_amount,
        return_of_id=int(return_of_id) if return_of_id else None,
        customer_id=int(customer_id) if customer_id else None,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
    )
    db.add(transaction)
    db.flush()

    # Update loyalty points for customer sales
    if transaction_type == "sale" and customer_id:
        customer = db.query(models.Customer).filter(
            models.Customer.id == int(customer_id),
            models.Customer.shop_id == shop.id
        ).first()
        if customer:
            # 1 point per whole dollar spent, floor to prevent splitting exploits
            points_earned = int(total_amount // 1)
            customer.loyalty_points = round(customer.loyalty_points + points_earned, 2)

    for product, qty, price, subtotal, line_discount in items_data:
        item = models.TransactionItem(
            transaction_id=transaction.id,
            product_id=product.id,
            quantity=qty,
            unit_price=price,
            discount_amount=line_discount,
            subtotal=subtotal,
        )
        db.add(item)

        # Update stock
        if transaction_type == "sale":
            product.stock_quantity -= qty
        elif transaction_type == "purchase":
            product.stock_quantity += qty
        elif transaction_type == "adjustment":
            product.stock_quantity = qty  # set absolute value for adjustments

    log_action(db, shop.id, request, transaction_type.upper(), "transaction", transaction.id,
                f"{transaction_type.title()} of {len(items_data)} item(s) — ${total_amount:.2f}")
    db.commit()
    return RedirectResponse(url="/transactions", status_code=302)


@router.get("/{transaction_id}", response_class=HTMLResponse)
async def transaction_detail(request: Request, transaction_id: int, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.shop_id == shop.id
    ).first()
    if not transaction:
        return RedirectResponse(url="/transactions", status_code=302)

    return templates.TemplateResponse("transactions/detail.html", {
        "request": request, "shop": shop, "transaction": transaction,
        "subtotal_before_discount": transaction.subtotal_before_discount
    })

# ── Returns ───────────────────────────────────────────────────────────────────

@router.get("/{transaction_id}/return", response_class=HTMLResponse)
async def return_form(request: Request, transaction_id: int,
                      db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/dashboard", status_code=302)
    original = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.SALE,
    ).first()
    if not original:
        return RedirectResponse(url="/transactions", status_code=302)
    return templates.TemplateResponse("transactions/return.html", {
        "request": request, "shop": shop, "original": original,
    })


@router.post("/{transaction_id}/return", response_class=HTMLResponse)
async def return_create(request: Request, transaction_id: int,
                        db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/dashboard", status_code=302)
    original = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.SALE,
    ).first()
    if not original:
        return RedirectResponse(url="/transactions", status_code=302)

    form = await request.form()
    notes = form.get("notes", "").strip() or f"Return of sale #{transaction_id}"
    total = 0.0

    return_txn = models.Transaction(
        shop_id=shop.id,
        transaction_type=models.TransactionType.RETURN,
        reference=f"RET-{transaction_id}",
        notes=notes,
        total_amount=0.0, tax_amount=0.0, tax_rate=0.0,
        return_of_id=transaction_id,
        customer_id=original.customer_id,
    )
    db.add(return_txn); db.flush()

    product_ids = form.getlist("product_id[]")
    quantities  = form.getlist("quantity[]")

    for pid_s, qty_s in zip(product_ids, quantities):
        try:
            pid = int(pid_s); qty = float(qty_s)
        except ValueError:
            continue
        if qty <= 0:
            continue
        product = db.query(models.Product).filter(
            models.Product.id == pid, models.Product.shop_id == shop.id
        ).first()
        if not product:
            continue
        # Find original item for price and max qty validation
        orig_item = next((i for i in original.items if i.product_id == pid), None)
        if not orig_item:
            continue
        # Validate return quantity doesn't exceed original
        if qty > orig_item.quantity:
            logger.warning("Attempted return of %.4f > original %.4f for product %s, capping quantity",
                           qty, orig_item.quantity, pid)
            qty = orig_item.quantity  # Cap at original quantity
        unit_price = orig_item.unit_price

        # Restock product
        product.stock_quantity = round(product.stock_quantity + qty, 4)
        sub = round(qty * unit_price, 2)
        total += sub

        db.add(models.TransactionItem(
            transaction_id=return_txn.id,
            product_id=pid,
            quantity=qty,
            unit_price=unit_price,
            subtotal=sub,
        ))

    return_txn.total_amount = round(total, 2)
    log_action(db, shop.id, request, "RETURN", "transaction", return_txn.id,
               f"Return against sale #{transaction_id}, restocked {len(product_ids)} product(s)")
    db.commit()
    return RedirectResponse(url=f"/transactions/{return_txn.id}", status_code=302)
