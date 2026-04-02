from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from audit import log_action, _sanitize_for_log
import models
import urllib.request
import urllib.error
import json

router = APIRouter(prefix="/products")
templates = Jinja2Templates(directory="templates")


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


def get_categories(shop_id: int, db: Session):
    return db.query(models.Category).filter(
        models.Category.shop_id == shop_id
    ).order_by(models.Category.name).all()


# ── Barcode lookup (Open Food Facts) ─────────────────────────────────────────

@router.get("/lookup", response_class=JSONResponse)
async def barcode_lookup(request: Request, barcode: str = "", db: Session = Depends(get_db)):
    """Look up a barcode via Open Food Facts and return product details as JSON."""
    shop = get_shop(request, db)
    if not shop:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    barcode = barcode.strip()
    if not barcode:
        return JSONResponse({"error": "No barcode provided"}, status_code=400)

    # Check if barcode already exists in this shop
    existing = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.sku == barcode,
        models.Product.is_active == True
    ).first()
    if existing:
        return JSONResponse({
            "duplicate": True,
            "product_id": existing.id,
            "name": existing.name,
        })

    # Query Open Food Facts
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StockTracker/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError:
        return JSONResponse({"error": "Could not reach Open Food Facts. Check your connection."}, status_code=502)
    except Exception:
        return JSONResponse({"error": "Lookup failed. Enter details manually."}, status_code=500)

    if data.get("status") != 1:
        # Product not found in database — return barcode so SKU is pre-filled
        return JSONResponse({"found": False, "barcode": barcode})

    p = data.get("product", {})

    name = (
        p.get("product_name_en")
        or p.get("product_name")
        or p.get("abbreviated_product_name")
        or ""
    ).strip()

    brand = p.get("brands", "").split(",")[0].strip()
    full_name = f"{brand} {name}".strip() if brand and name else (name or brand)

    description_parts = []
    if p.get("quantity"):
        description_parts.append(p["quantity"])
    if p.get("categories_tags"):
        cats = [c.replace("en:", "").replace("-", " ").title()
                for c in p["categories_tags"][:3] if c.startswith("en:")]
        if cats:
            description_parts.append(", ".join(cats))
    if p.get("ingredients_text_en"):
        description_parts.append(p["ingredients_text_en"][:200])

    description = " — ".join(description_parts) if description_parts else ""

    image_url = (
        p.get("image_front_small_url")
        or p.get("image_small_url")
        or p.get("image_url")
        or ""
    )

    return JSONResponse({
        "found": True,
        "barcode": barcode,
        "name": full_name,
        "description": description,
        "image_url": image_url,
        "brand": brand,
        "quantity": p.get("quantity", ""),
    })


# ── Scan page ────────────────────────────────────────────────────────────────

@router.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("products/scan.html", {
        "request": request,
        "shop": shop,
        "categories": get_categories(shop.id, db),
    })


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def products_list(
    request: Request, db: Session = Depends(get_db),
    search: str = "", category_id: str = ""
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    query = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True
    )
    if search:
        # Escape LIKE wildcards
        esc = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(models.Product.name.ilike(f"%{esc}%", escape='\\'))
    if category_id and category_id.isdigit():
        query = query.filter(models.Product.category_id == int(category_id))

    products = query.order_by(models.Product.name).all()
    categories = get_categories(shop.id, db)

    return templates.TemplateResponse("products/index.html", {
        "request": request, "shop": shop, "products": products,
        "search": search, "categories": categories,
        "selected_category": category_id
    })


# ── Create ───────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def product_new(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("products/form.html", {
        "request": request, "shop": shop, "product": None, "error": None,
        "categories": get_categories(shop.id, db)
    })


@router.post("/new", response_class=HTMLResponse)
async def product_create(
    request: Request,
    name: str = Form(...),
    sku: str = Form(default=""),
    category_id: str = Form(default=""),
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

    product = models.Product(
        shop_id=shop.id,
        name=name,
        sku=sku or None,
        category_id=int(category_id) if category_id and category_id.isdigit() else None,
        description=description or None,
        unit=unit,
        cost_price=cost_price,
        selling_price=selling_price,
        stock_quantity=stock_quantity,
        low_stock_threshold=low_stock_threshold,
    )
    db.add(product)
    db.flush()
    log_action(db, shop.id, request, "CREATE_PRODUCT", "product", product.id,
                f"Created product: {_sanitize_for_log(product.name)}")
    db.commit()
    return RedirectResponse(url="/products", status_code=302)


# ── Edit ─────────────────────────────────────────────────────────────────────

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
        "request": request, "shop": shop, "product": product, "error": None,
        "categories": get_categories(shop.id, db)
    })


@router.post("/{product_id}/edit", response_class=HTMLResponse)
async def product_update(
    request: Request,
    product_id: int,
    name: str = Form(...),
    sku: str = Form(default=""),
    category_id: str = Form(default=""),
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
    product.category_id = int(category_id) if category_id and category_id.isdigit() else None
    product.description = description or None
    product.unit = unit
    product.cost_price = cost_price
    product.selling_price = selling_price
    product.stock_quantity = stock_quantity
    product.low_stock_threshold = low_stock_threshold
    log_action(db, shop.id, request, "EDIT_PRODUCT", "product", product.id,
                f"Edited product: {_sanitize_for_log(product.name)}")
    db.commit()
    return RedirectResponse(url="/products", status_code=302)


# ── Delete ───────────────────────────────────────────────────────────────────

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
        log_action(db, shop.id, request, "DELETE_PRODUCT", "product", product.id,
                    f"Deleted product: {_sanitize_for_log(product.name)}")
        db.commit()
    return RedirectResponse(url="/products", status_code=302)
