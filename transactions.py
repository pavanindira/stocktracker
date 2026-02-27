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

    total_amount = 0.0
    items_data = []
    for pid, qty, price in zip(product_ids, quantities, unit_prices):
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
        subtotal = qty_f * price_f
        total_amount += subtotal
        items_data.append((product, qty_f, price_f, subtotal))

    transaction = models.Transaction(
        shop_id=shop.id,
        transaction_type=models.TransactionType(transaction_type),
        reference=reference or None,
        notes=notes or None,
        total_amount=total_amount,
    )
    db.add(transaction)
    db.flush()

    for product, qty, price, subtotal in items_data:
        item = models.TransactionItem(
            transaction_id=transaction.id,
            product_id=product.id,
            quantity=qty,
            unit_price=price,
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
        "request": request, "shop": shop, "transaction": transaction
    })
