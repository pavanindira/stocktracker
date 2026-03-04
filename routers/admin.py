from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models, auth

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


def get_admin(request: Request, db: Session):
    """Return admin shop or None."""
    try:
        return auth.require_admin(request, db)
    except Exception:
        return None


# ── Admin Dashboard ──────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_home(request: Request, db: Session = Depends(get_db)):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    shops = db.query(models.Shop).filter(models.Shop.is_admin == False).order_by(models.Shop.created_at.desc()).all()

    # Enrich each shop with stats
    shop_stats = []
    for shop in shops:
        product_count = db.query(func.count(models.Product.id)).filter(
            models.Product.shop_id == shop.id,
            models.Product.is_active == True
        ).scalar()
        txn_count = db.query(func.count(models.Transaction.id)).filter(
            models.Transaction.shop_id == shop.id
        ).scalar()
        low_stock = db.query(func.count(models.Product.id)).filter(
            models.Product.shop_id == shop.id,
            models.Product.is_active == True,
            models.Product.stock_quantity <= models.Product.low_stock_threshold
        ).scalar()
        shop_stats.append({
            "shop": shop,
            "product_count": product_count,
            "txn_count": txn_count,
            "low_stock": low_stock,
        })

    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "admin": admin,
        "shop_stats": shop_stats,
        "total_shops": len(shops),
        "active_shops": sum(1 for s in shops if s.is_active),
    })


# ── Create Shop ──────────────────────────────────────────────────────────────

@router.get("/shops/new", response_class=HTMLResponse)
async def shop_new(request: Request, db: Session = Depends(get_db)):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("admin/shop_form.html", {
        "request": request, "admin": admin, "shop": None, "error": None
    })


@router.post("/shops/new", response_class=HTMLResponse)
async def shop_create(
    request: Request,
    shop_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(default=""),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    error = None
    if password != confirm_password:
        error = "Passwords do not match."
    elif db.query(models.Shop).filter(models.Shop.username == username).first():
        error = f"Username '{username}' is already taken."
    elif email and db.query(models.Shop).filter(models.Shop.email == email).first():
        error = f"Email '{email}' is already in use."

    if error:
        return templates.TemplateResponse("admin/shop_form.html", {
            "request": request, "admin": admin, "shop": None, "error": error
        })

    shop = models.Shop(
        name=shop_name,
        username=username,
        email=email or None,
        password_hash=auth.hash_password(password),
        is_admin=False,
        is_active=True,
    )
    db.add(shop)
    db.commit()
    return RedirectResponse(url="/admin?created=1", status_code=302)


# ── Edit Shop ────────────────────────────────────────────────────────────────

@router.get("/shops/{shop_id}/edit", response_class=HTMLResponse)
async def shop_edit(request: Request, shop_id: int, db: Session = Depends(get_db)):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id, models.Shop.is_admin == False
    ).first()
    if not shop:
        return RedirectResponse(url="/admin", status_code=302)

    return templates.TemplateResponse("admin/shop_form.html", {
        "request": request, "admin": admin, "shop": shop, "error": None
    })


@router.post("/shops/{shop_id}/edit", response_class=HTMLResponse)
async def shop_update(
    request: Request,
    shop_id: int,
    shop_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(default=""),
    db: Session = Depends(get_db)
):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id, models.Shop.is_admin == False
    ).first()
    if not shop:
        return RedirectResponse(url="/admin", status_code=302)

    # Check username uniqueness (excluding self)
    duplicate_username = db.query(models.Shop).filter(
        models.Shop.username == username, models.Shop.id != shop_id
    ).first()
    if duplicate_username:
        return templates.TemplateResponse("admin/shop_form.html", {
            "request": request, "admin": admin, "shop": shop,
            "error": f"Username '{username}' is already taken."
        })

    shop.name = shop_name
    shop.username = username
    shop.email = email or None
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)


# ── Reset Password ───────────────────────────────────────────────────────────

@router.get("/shops/{shop_id}/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, shop_id: int, db: Session = Depends(get_db)):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id, models.Shop.is_admin == False
    ).first()
    if not shop:
        return RedirectResponse(url="/admin", status_code=302)

    return templates.TemplateResponse("admin/reset_password.html", {
        "request": request, "admin": admin, "shop": shop, "error": None, "success": False
    })


@router.post("/shops/{shop_id}/reset-password", response_class=HTMLResponse)
async def reset_password_post(
    request: Request,
    shop_id: int,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id, models.Shop.is_admin == False
    ).first()
    if not shop:
        return RedirectResponse(url="/admin", status_code=302)

    if new_password != confirm_password:
        return templates.TemplateResponse("admin/reset_password.html", {
            "request": request, "admin": admin, "shop": shop,
            "error": "Passwords do not match.", "success": False
        })
    if len(new_password) < 6:
        return templates.TemplateResponse("admin/reset_password.html", {
            "request": request, "admin": admin, "shop": shop,
            "error": "Password must be at least 6 characters.", "success": False
        })

    shop.password_hash = auth.hash_password(new_password)
    db.commit()
    return templates.TemplateResponse("admin/reset_password.html", {
        "request": request, "admin": admin, "shop": shop, "error": None, "success": True
    })


# ── Toggle Active / Deactivate ───────────────────────────────────────────────

@router.post("/shops/{shop_id}/toggle-active")
async def toggle_active(request: Request, shop_id: int, db: Session = Depends(get_db)):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id, models.Shop.is_admin == False
    ).first()
    if shop:
        shop.is_active = not shop.is_active
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)


# ── Admin: Change own password ───────────────────────────────────────────────

@router.get("/change-password", response_class=HTMLResponse)
async def change_admin_password_page(request: Request, db: Session = Depends(get_db)):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("admin/change_password.html", {
        "request": request, "admin": admin, "error": None, "success": False
    })


@router.post("/change-password", response_class=HTMLResponse)
async def change_admin_password_post(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = get_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)

    if not auth.verify_password(current_password, admin.password_hash):
        return templates.TemplateResponse("admin/change_password.html", {
            "request": request, "admin": admin,
            "error": "Current password is incorrect.", "success": False
        })
    if new_password != confirm_password:
        return templates.TemplateResponse("admin/change_password.html", {
            "request": request, "admin": admin,
            "error": "New passwords do not match.", "success": False
        })
    if len(new_password) < 6:
        return templates.TemplateResponse("admin/change_password.html", {
            "request": request, "admin": admin,
            "error": "Password must be at least 6 characters.", "success": False
        })

    admin.password_hash = auth.hash_password(new_password)
    db.commit()
    return templates.TemplateResponse("admin/change_password.html", {
        "request": request, "admin": admin, "error": None, "success": True
    })
