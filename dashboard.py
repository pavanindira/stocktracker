from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models, auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def require_auth(request: Request, db: Session = Depends(get_db)):
    try:
        return auth.get_current_shop(request, db)
    except Exception:
        return None


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return RedirectResponse(url="/login", status_code=302)

    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    products = db.query(models.Product).filter(
        models.Product.shop_id == shop_id,
        models.Product.is_active == True
    ).all()

    low_stock = [p for p in products if p.is_low_stock]
    total_products = len(products)
    total_stock_value = sum(p.stock_value for p in products)

    # Recent transactions
    recent_transactions = db.query(models.Transaction).filter(
        models.Transaction.shop_id == shop_id
    ).order_by(models.Transaction.created_at.desc()).limit(5).all()

    # Sales & purchases totals this month
    from datetime import datetime
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    monthly_sales = db.query(func.sum(models.Transaction.total_amount)).filter(
        models.Transaction.shop_id == shop_id,
        models.Transaction.transaction_type == models.TransactionType.SALE,
        models.Transaction.created_at >= month_start
    ).scalar() or 0.0

    monthly_purchases = db.query(func.sum(models.Transaction.total_amount)).filter(
        models.Transaction.shop_id == shop_id,
        models.Transaction.transaction_type == models.TransactionType.PURCHASE,
        models.Transaction.created_at >= month_start
    ).scalar() or 0.0

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "shop": shop,
        "total_products": total_products,
        "low_stock_count": len(low_stock),
        "low_stock_items": low_stock[:5],
        "total_stock_value": total_stock_value,
        "recent_transactions": recent_transactions,
        "monthly_sales": monthly_sales,
        "monthly_purchases": monthly_purchases,
    })
