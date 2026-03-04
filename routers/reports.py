from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from datetime import datetime, timedelta
import models
import fefo, auth
import csv
import io

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="templates")


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


@router.get("", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    db: Session = Depends(get_db),
    start_date: str = "",
    end_date: str = "",
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/dashboard", status_code=302)

    # Default: last 30 days
    if not end_date:
        end_dt = datetime.now()
        end_date = end_dt.strftime("%Y-%m-%d")
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    if not start_date:
        start_dt = end_dt - timedelta(days=30)
        start_date = start_dt.strftime("%Y-%m-%d")
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    end_dt_full = end_dt.replace(hour=23, minute=59, second=59)

    # Sales summary
    sales = db.query(models.Transaction).filter(
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.SALE,
        models.Transaction.created_at >= start_dt,
        models.Transaction.created_at <= end_dt_full
    ).all()

    purchases = db.query(models.Transaction).filter(
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.PURCHASE,
        models.Transaction.created_at >= start_dt,
        models.Transaction.created_at <= end_dt_full
    ).all()

    total_sales = sum(t.total_amount for t in sales)
    total_purchases = sum(t.total_amount for t in purchases)

    # Top selling products
    top_products = db.query(
        models.Product.name,
        func.sum(models.TransactionItem.quantity).label("total_qty"),
        func.sum(models.TransactionItem.subtotal).label("total_revenue")
    ).join(models.TransactionItem, models.Product.id == models.TransactionItem.product_id
    ).join(models.Transaction, models.TransactionItem.transaction_id == models.Transaction.id
    ).filter(
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.SALE,
        models.Transaction.created_at >= start_dt,
        models.Transaction.created_at <= end_dt_full
    ).group_by(models.Product.name
    ).order_by(func.sum(models.TransactionItem.subtotal).desc()
    ).limit(10).all()

    # Current stock
    products = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True
    ).order_by(models.Product.name).all()

    low_stock = [p for p in products if p.is_low_stock]
    total_stock_value = sum(p.stock_value for p in products)

    return templates.TemplateResponse("reports/index.html", {
        "request": request,
        "shop": shop,
        "start_date": start_date,
        "end_date": end_date,
        "total_sales": total_sales,
        "total_purchases": total_purchases,
        "sales_count": len(sales),
        "purchases_count": len(purchases),
        "top_products": top_products,
        "products": products,
        "low_stock": low_stock,
        "total_stock_value": total_stock_value,
    })




@router.get("/expiry", response_class=HTMLResponse)
async def expiry_report(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/dashboard", status_code=302)

    warnings = fefo.expiry_warnings(shop.id, db)
    return templates.TemplateResponse("reports/expiry.html", {
        "request": request, "shop": shop,
        **warnings,
    })

@router.get("/export/stock")
async def export_stock_csv(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    products = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True
    ).order_by(models.Product.name).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "SKU", "Category", "Unit", "Stock Qty", "Low Stock Threshold",
                     "Cost Price", "Selling Price", "Stock Value", "Status"])
    for p in products:
        writer.writerow([
            p.name, p.sku or "", p.category or "", p.unit,
            p.stock_quantity, p.low_stock_threshold,
            p.cost_price, p.selling_price,
            round(p.stock_value, 2),
            "LOW STOCK" if p.is_low_stock else "OK"
        ])

    output.seek(0)
    filename = f"stock_{shop.username}_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/transactions")
async def export_transactions_csv(
    request: Request,
    db: Session = Depends(get_db),
    start_date: str = "",
    end_date: str = ""
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    query = db.query(models.Transaction).filter(models.Transaction.shop_id == shop.id)
    if start_date:
        query = query.filter(models.Transaction.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        query = query.filter(models.Transaction.created_at <= end_dt)
    transactions = query.order_by(models.Transaction.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Type", "Reference", "Product", "Quantity", "Unit Price", "Subtotal", "Notes"])
    for t in transactions:
        for item in t.items:
            writer.writerow([
                t.created_at.strftime("%Y-%m-%d %H:%M"),
                t.transaction_type.value,
                t.reference or "",
                item.product.name,
                item.quantity,
                item.unit_price,
                item.subtotal,
                t.notes or ""
            ])

    output.seek(0)
    filename = f"transactions_{shop.username}_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
