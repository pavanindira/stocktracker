from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models

router = APIRouter(prefix="/categories")
templates = Jinja2Templates(directory="templates")

PRESET_COLORS = [
    "#7c6af7", "#f5a623", "#2ecc71", "#4ecdc4",
    "#e74c3c", "#3498db", "#9b59b6", "#e67e22",
    "#1abc9c", "#e91e63", "#607d8b", "#795548",
]


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


@router.get("", response_class=HTMLResponse)
async def categories_list(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    categories = db.query(models.Category).filter(
        models.Category.shop_id == shop.id
    ).order_by(models.Category.name).all()

    return templates.TemplateResponse("categories/index.html", {
        "request": request, "shop": shop, "categories": categories
    })


@router.get("/new", response_class=HTMLResponse)
async def category_new(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("categories/form.html", {
        "request": request, "shop": shop, "category": None,
        "error": None, "colors": PRESET_COLORS
    })


@router.post("/new", response_class=HTMLResponse)
async def category_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    color: str = Form(default="#7c6af7"),
    db: Session = Depends(get_db)
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    # Check for duplicate name within this shop
    existing = db.query(models.Category).filter(
        models.Category.shop_id == shop.id,
        models.Category.name.ilike(name.strip())
    ).first()
    if existing:
        return templates.TemplateResponse("categories/form.html", {
            "request": request, "shop": shop, "category": None,
            "error": f"A category named '{name}' already exists.",
            "colors": PRESET_COLORS
        })

    category = models.Category(
        shop_id=shop.id,
        name=name.strip(),
        description=description.strip() or None,
        color=color,
    )
    db.add(category)
    db.commit()
    return RedirectResponse(url="/categories", status_code=302)


@router.get("/{category_id}/edit", response_class=HTMLResponse)
async def category_edit(request: Request, category_id: int, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    category = db.query(models.Category).filter(
        models.Category.id == category_id,
        models.Category.shop_id == shop.id
    ).first()
    if not category:
        return RedirectResponse(url="/categories", status_code=302)

    return templates.TemplateResponse("categories/form.html", {
        "request": request, "shop": shop, "category": category,
        "error": None, "colors": PRESET_COLORS
    })


@router.post("/{category_id}/edit", response_class=HTMLResponse)
async def category_update(
    request: Request,
    category_id: int,
    name: str = Form(...),
    description: str = Form(default=""),
    color: str = Form(default="#7c6af7"),
    db: Session = Depends(get_db)
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    category = db.query(models.Category).filter(
        models.Category.id == category_id,
        models.Category.shop_id == shop.id
    ).first()
    if not category:
        return RedirectResponse(url="/categories", status_code=302)

    # Check duplicate name (excluding self)
    duplicate = db.query(models.Category).filter(
        models.Category.shop_id == shop.id,
        models.Category.name.ilike(name.strip()),
        models.Category.id != category_id
    ).first()
    if duplicate:
        return templates.TemplateResponse("categories/form.html", {
            "request": request, "shop": shop, "category": category,
            "error": f"A category named '{name}' already exists.",
            "colors": PRESET_COLORS
        })

    category.name = name.strip()
    category.description = description.strip() or None
    category.color = color
    db.commit()
    return RedirectResponse(url="/categories", status_code=302)


@router.post("/{category_id}/delete")
async def category_delete(request: Request, category_id: int, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    category = db.query(models.Category).filter(
        models.Category.id == category_id,
        models.Category.shop_id == shop.id
    ).first()

    if category:
        # Unlink products rather than block deletion
        db.query(models.Product).filter(
            models.Product.category_id == category_id
        ).update({"category_id": None})
        db.delete(category)
        db.commit()

    return RedirectResponse(url="/categories", status_code=302)
