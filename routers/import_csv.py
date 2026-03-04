"""
Bulk product import via CSV upload.
Routes:
  GET  /products/import           — upload form + template download
  POST /products/import/preview   — parse CSV, return validation table (no DB write)
  POST /products/import/commit    — write validated rows to DB
"""
import csv, io, json
from fastapi import APIRouter, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth

router     = APIRouter(prefix="/products/import")
templates  = Jinja2Templates(directory="templates")

# Expected CSV columns (case-insensitive, order-independent)
REQUIRED_COLS = {"name"}
OPTIONAL_COLS = {
    "sku", "category", "description", "unit",
    "cost_price", "selling_price", "stock_quantity", "low_stock_threshold",
}
ALL_COLS = REQUIRED_COLS | OPTIONAL_COLS

TEMPLATE_ROWS = [
    ["name", "sku", "category", "description", "unit",
     "cost_price", "selling_price", "stock_quantity", "low_stock_threshold"],
    ["Coca-Cola 500ml", "5449000000996", "Beverages",
     "Carbonated soft drink", "pcs", "0.60", "1.20", "48", "12"],
    ["Rice 1kg", "RICE001", "Dry Goods",
     "Long grain white rice", "kg", "0.90", "1.80", "30", "10"],
]

MAX_ROWS = 2000


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


# ── Template download ─────────────────────────────────────────────────────────

@router.get("/template")
async def download_template():
    buf = io.StringIO()
    w   = csv.writer(buf)
    for row in TEMPLATE_ROWS:
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="products_template.csv"'},
    )


# ── Upload form ───────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def import_form(request: Request, db: Session = Depends(get_db)):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/products", status_code=302)
    return templates.TemplateResponse("products/import.html", {
        "request": request, "shop": shop,
        "preview": None, "error": None,
    })


# ── Parse & preview (no DB write) ────────────────────────────────────────────

@router.post("/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    on_duplicate: str = Form(default="skip"),   # skip | update
    db: Session = Depends(get_db),
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/products", status_code=302)

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")   # handle BOM
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    rows, error = _parse_csv(text, shop, db, on_duplicate)

    return templates.TemplateResponse("products/import.html", {
        "request": request, "shop": shop, "error": error,
        "preview": rows, "on_duplicate": on_duplicate,
        "filename": file.filename,
        "csv_data": json.dumps([r for r in rows if r["status"] != "error"])
            if not error else None,
    })


# ── Commit validated rows ─────────────────────────────────────────────────────

@router.post("/commit", response_class=HTMLResponse)
async def import_commit(
    request: Request,
    csv_data: str = Form(...),
    on_duplicate: str = Form(default="skip"),
    db: Session = Depends(get_db),
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/products", status_code=302)

    try:
        rows = json.loads(csv_data)
    except Exception:
        return RedirectResponse(url="/products/import?error=bad_data", status_code=302)

    created = updated = skipped = 0

    # Pre-load categories for this shop
    cats = {c.name.lower(): c for c in
            db.query(models.Category).filter(
                models.Category.shop_id == shop.id).all()}

    for row in rows:
        if row.get("status") == "error":
            continue

        name       = row["name"].strip()
        sku        = row.get("sku", "").strip() or None
        cat_name   = row.get("category", "").strip()

        # Resolve or create category
        cat_id = None
        if cat_name:
            key = cat_name.lower()
            if key not in cats:
                new_cat = models.Category(shop_id=shop.id, name=cat_name)
                db.add(new_cat)
                db.flush()
                cats[key] = new_cat
            cat_id = cats[cat_name.lower()].id

        # Check for existing by SKU or name
        existing = None
        if sku:
            existing = db.query(models.Product).filter(
                models.Product.shop_id == shop.id,
                models.Product.sku == sku,
                models.Product.is_active == True,
            ).first()
        if not existing:
            existing = db.query(models.Product).filter(
                models.Product.shop_id == shop.id,
                models.Product.name.ilike(name),
                models.Product.is_active == True,
            ).first()

        if existing:
            if on_duplicate == "update":
                existing.name                = name
                existing.sku                 = sku
                existing.category_id         = cat_id
                existing.description         = row.get("description") or existing.description
                existing.unit                = row.get("unit") or existing.unit or "pcs"
                existing.cost_price          = _f(row.get("cost_price"), existing.cost_price)
                existing.selling_price       = _f(row.get("selling_price"), existing.selling_price)
                existing.stock_quantity      = _f(row.get("stock_quantity"), existing.stock_quantity)
                existing.low_stock_threshold = _f(row.get("low_stock_threshold"), existing.low_stock_threshold)
                updated += 1
            else:
                skipped += 1
        else:
            db.add(models.Product(
                shop_id=shop.id, name=name, sku=sku,
                category_id=cat_id,
                description=row.get("description") or None,
                unit=row.get("unit") or "pcs",
                cost_price=_f(row.get("cost_price"), 0),
                selling_price=_f(row.get("selling_price"), 0),
                stock_quantity=_f(row.get("stock_quantity"), 0),
                low_stock_threshold=_f(row.get("low_stock_threshold"), 10),
            ))
            created += 1

    db.commit()

    return templates.TemplateResponse("products/import_done.html", {
        "request": request, "shop": shop,
        "created": created, "updated": updated, "skipped": skipped,
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_csv(text: str, shop, db: Session, on_duplicate: str):
    """Parse CSV text → list of row dicts with status/error fields."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], "The CSV file appears to be empty."

    # Normalise header names
    header_map = {h.strip().lower(): h for h in reader.fieldnames}
    missing    = REQUIRED_COLS - set(header_map.keys())
    if missing:
        return [], f"Missing required column(s): {', '.join(missing)}"

    # Pre-load existing products (sku → id, lower(name) → id)
    sku_map  = {p.sku: p.id for p in db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
        models.Product.sku != None).all()}
    name_map = {p.name.lower(): p.id for p in db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True).all()}

    rows = []
    for i, raw in enumerate(reader):
        if i >= MAX_ROWS:
            break
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items()}

        name = row.get("name", "").strip()
        sku  = row.get("sku", "").strip()
        r    = {
            "row": i + 2,   # 1-based + header
            "name": name,
            "sku": sku,
            "category": row.get("category", ""),
            "description": row.get("description", ""),
            "unit": row.get("unit", "pcs") or "pcs",
            "cost_price": row.get("cost_price", "0"),
            "selling_price": row.get("selling_price", "0"),
            "stock_quantity": row.get("stock_quantity", "0"),
            "low_stock_threshold": row.get("low_stock_threshold", "10"),
            "status": "create",
            "error": "",
        }

        # Validation
        if not name:
            r["status"] = "error"
            r["error"]  = "Name is required"
        elif not _valid_num(r["cost_price"]):
            r["status"] = "error"
            r["error"]  = "Invalid cost_price"
        elif not _valid_num(r["selling_price"]):
            r["status"] = "error"
            r["error"]  = "Invalid selling_price"
        elif not _valid_num(r["stock_quantity"]):
            r["status"] = "error"
            r["error"]  = "Invalid stock_quantity"
        elif not _valid_num(r["low_stock_threshold"]):
            r["status"] = "error"
            r["error"]  = "Invalid low_stock_threshold"
        else:
            # Duplicate detection
            dup = (sku and sku in sku_map) or (name.lower() in name_map)
            if dup:
                r["status"] = "update" if on_duplicate == "update" else "skip"

        rows.append(r)

    if not rows:
        return [], "No data rows found in the CSV."
    return rows, None


def _valid_num(v: str) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return not v   # empty string is OK (will default)


def _f(v, default):
    try:
        return float(v) if v else default
    except (ValueError, TypeError):
        return default
