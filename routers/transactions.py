from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
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

    return templates.TemplateResponse("transactions/form.html", {
        "request": request, "shop": shop, "products": products,
        "transaction_type": type, "error": None
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
        tax_rate=tax_rate,
        tax_amount=tax_amount,
    )
    db.add(transaction)
    db.flush()

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
