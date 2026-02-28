from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import ValidationError
from database import get_db
import models, auth, schemas

router = APIRouter(prefix="/products")
templates = Jinja2Templates(directory="templates")


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


@router.get("", response_class=HTMLResponse)
async def products_list(request: Request, db: Session = Depends(get_db), search: str = ""):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    query = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True
    )
    if search:
        query = query.filter(models.Product.name.ilike(f"%{search}%"))
    products = query.order_by(models.Product.name).all()

    return templates.TemplateResponse("products/index.html", {
        "request": request, "shop": shop, "products": products, "search": search
    })


@router.get("/new", response_class=HTMLResponse)
async def product_new(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("products/form.html", {
        "request": request, "shop": shop, "product": None, "error": None
    })


@router.post("/new", response_class=HTMLResponse)
async def product_create(
    request: Request,
    name: str = Form(...),
    sku: str = Form(default=""),
    category: str = Form(default=""),
    description: str = Form(default=""),
    unit: str = Form(default="pcs"),
    cost_price: float = Form(default=0.0),
    selling_price: float = Form(default=0.0),
    stock_quantity: float = Form(default=0.0),
    low_stock_threshold: float = Form(default=10.0),
    db: Session = Depends(get_db)
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    # Validate with Pydantic
    try:
        validated = schemas.ProductCreate(
            name=name,
            sku=sku or None,
            category=category or None,
            description=description or None,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            stock_quantity=stock_quantity,
            low_stock_threshold=low_stock_threshold,
        )
    except ValidationError as e:
        error_msg = e.errors()[0]['msg'] if e.errors() else "Validation error"
        products = db.query(models.Product).filter(
            models.Product.shop_id == shop.id,
            models.Product.is_active == True
        ).order_by(models.Product.name).all()
        return templates.TemplateResponse("products/index.html", {
            "request": request, "shop": shop, "products": products, "search": "", "error": error_msg
        })

    product = models.Product(
        shop_id=shop.id,
        name=validated.name,
        sku=validated.sku,
        category=validated.category,
        description=validated.description,
        unit=validated.unit,
        cost_price=validated.cost_price,
        selling_price=validated.selling_price,
        stock_quantity=validated.stock_quantity,
        low_stock_threshold=validated.low_stock_threshold,
    )
    db.add(product)
    db.commit()
    return RedirectResponse(url="/products", status_code=302)


@router.get("/{product_id}/edit", response_class=HTMLResponse)
async def product_edit(request: Request, product_id: int, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.shop_id == shop.id
    ).first()
    if not product:
        return RedirectResponse(url="/products", status_code=302)

    return templates.TemplateResponse("products/form.html", {
        "request": request, "shop": shop, "product": product, "error": None
    })


@router.post("/{product_id}/edit", response_class=HTMLResponse)
async def product_update(
    request: Request,
    product_id: int,
    name: str = Form(...),
    sku: str = Form(default=""),
    category: str = Form(default=""),
    description: str = Form(default=""),
    unit: str = Form(default="pcs"),
    cost_price: float = Form(default=0.0),
    selling_price: float = Form(default=0.0),
    stock_quantity: float = Form(default=0.0),
    low_stock_threshold: float = Form(default=10.0),
    db: Session = Depends(get_db)
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.shop_id == shop.id
    ).first()
    if not product:
        return RedirectResponse(url="/products", status_code=302)

    product.name = name
    product.sku = sku or None
    product.category = category or None
    product.description = description or None
    product.unit = unit
    
    # Validate with Pydantic
    try:
        validated = schemas.ProductUpdate(
            name=name,
            sku=sku or None,
            category=category or None,
            description=description or None,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            stock_quantity=stock_quantity,
            low_stock_threshold=low_stock_threshold,
        )
    except ValidationError as e:
        error_msg = e.errors()[0]['msg'] if e.errors() else "Validation error"
        return templates.TemplateResponse("products/form.html", {
            "request": request, "shop": shop, "product": product, "error": error_msg
        })

    product.name = validated.name
    product.sku = validated.sku
    product.category = validated.category
    product.description = validated.description
    product.unit = validated.unit
    product.cost_price = validated.cost_price
    product.selling_price = validated.selling_price
    product.stock_quantity = validated.stock_quantity
    product.low_stock_threshold = validated.low_stock_threshold
    db.commit()
    return RedirectResponse(url="/products", status_code=302)


@router.post("/{product_id}/delete")
async def product_delete(request: Request, product_id: int, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.shop_id == shop.id
    ).first()
    if product:
        product.is_active = False
        db.commit()
    return RedirectResponse(url="/products", status_code=302)
