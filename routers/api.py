"""
Mobile REST API — JWT-authenticated JSON endpoints for the Flutter app.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from jose import JWTError, jwt
from datetime import datetime, timedelta
from database import get_db
import models, auth as auth_mod
import fefo
import os, io, json
import urllib.request, urllib.error

# PDF / QR
from fpdf import FPDF
import qrcode
from PIL import Image

router = APIRouter(prefix="/api")

SECRET_KEY  = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
ALGORITHM   = "HS256"
TOKEN_HOURS = 24 * 7

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(shop_id: int, role: str, sub_user_id: int | None = None) -> str:
    payload = {
        "sub": str(shop_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS),
    }
    if sub_user_id:
        payload["uid"] = sub_user_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_session(token: str = Depends(oauth2_scheme),
                        db: Session = Depends(get_db)):
    exc = HTTPException(status_code=401, detail="Invalid or expired token",
                        headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        shop_id = int(payload["sub"])
        role    = payload.get("role", "owner")
        uid     = payload.get("uid")
    except (JWTError, TypeError, ValueError, KeyError):
        raise exc
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id, models.Shop.is_active == True
    ).first()
    if not shop or shop.is_admin:
        raise exc
    return {"shop": shop, "role": role, "sub_user_id": uid}


def _role_level(role: str) -> int:
    return {"cashier": 1, "manager": 2, "owner": 3}.get(role, 1)


def require_role(session: dict, min_role: str):
    if _role_level(session["role"]) < _role_level(min_role):
        raise HTTPException(status_code=403,
                            detail="Your role does not allow this action.")


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # 1. Try owner account
    shop = db.query(models.Shop).filter(models.Shop.username == form.username).first()
    if shop:
        if not auth_mod.verify_password(form.password, shop.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not shop.is_active:
            raise HTTPException(status_code=403, detail="Account deactivated")
        if shop.is_admin:
            raise HTTPException(status_code=403, detail="Admin accounts cannot use the mobile app")
        return {
            "access_token": create_token(shop.id, "owner"),
            "token_type": "bearer",
            "shop_id": shop.id,
            "shop_name": shop.name,
            "role": "owner",
        }

    # 2. Try sub-user
    sub = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.username == form.username
    ).first()
    if sub:
        if not auth_mod.verify_password(form.password, sub.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not sub.is_active:
            raise HTTPException(status_code=403, detail="Account deactivated")
        owner = db.query(models.Shop).filter(models.Shop.id == sub.shop_id).first()
        if not owner or not owner.is_active:
            raise HTTPException(status_code=403, detail="Shop account is inactive")
        return {
            "access_token": create_token(owner.id, sub.role.value, sub.id),
            "token_type": "bearer",
            "shop_id": owner.id,
            "shop_name": owner.name,
            "role": sub.role.value,
            "user_name": sub.name,
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(session=Depends(get_current_session), db: Session = Depends(get_db)):
    shop = session["shop"]
    role = session["role"]
    products = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True
    ).all()
    low_stock = [
        {"id": p.id, "name": p.name, "stock": p.stock_quantity,
         "threshold": p.low_stock_threshold, "unit": p.unit}
        for p in products if p.is_low_stock
    ]
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_sales = db.query(func.sum(models.Transaction.total_amount)).filter(
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.SALE,
        models.Transaction.created_at >= month_start
    ).scalar() or 0.0

    warnings = fefo.expiry_warnings(shop.id, db)

    data = {
        "total_products":  len(products),
        "low_stock_count": len(low_stock),
        "low_stock_items": low_stock,
        "monthly_sales":   round(monthly_sales, 2),
        "expired_count":   len(warnings["expired"]),
        "expiring_count":  len(warnings["expiring_soon"]),
        "expiring_soon":   [
            {
                "id":          w["product"].id,
                "name":        w["product"].name,
                "expiry_date": min(
                    (b.expiry_date.isoformat() for b in w["batches"] if b.expiry_date),
                    default=None,
                ),
                "status": "expired" if any(
                    b.expiry_date and b.expiry_date < warnings["today"]
                    for b in w["batches"]) else "soon",
            }
            for w in (warnings["expired"] + warnings["expiring_soon"])[:10]
        ],
    }
    if _role_level(role) >= _role_level("manager"):
        data["total_stock_value"] = round(sum(p.stock_value for p in products), 2)
    return data


# ── Team (owner only) ─────────────────────────────────────────────────────────

@router.get("/team")
def list_team(session=Depends(get_current_session), db: Session = Depends(get_db)):
    require_role(session, "owner")
    shop = session["shop"]
    members = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.shop_id == shop.id
    ).order_by(models.ShopSubUser.created_at).all()
    return [_sub_user_json(m) for m in members]


@router.post("/team", status_code=201)
def create_team_member(payload: dict, session=Depends(get_current_session),
                       db: Session = Depends(get_db)):
    require_role(session, "owner")
    shop = session["shop"]
    username = (payload.get("username") or "").strip()
    name     = (payload.get("name") or "").strip()
    password = payload.get("password", "")
    role     = payload.get("role", "cashier")

    if not username or not name or not password:
        raise HTTPException(400, "name, username, and password are required")
    if role not in ("manager", "cashier"):
        raise HTTPException(400, "role must be 'manager' or 'cashier'")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    taken = (db.query(models.Shop).filter(models.Shop.username == username).first() or
             db.query(models.ShopSubUser).filter(
                 models.ShopSubUser.username == username).first())
    if taken:
        raise HTTPException(409, f"Username '{username}' is already taken")

    sub = models.ShopSubUser(
        shop_id=shop.id, name=name, username=username,
        password_hash=auth_mod.hash_password(password),
        role=models.UserRole(role),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return _sub_user_json(sub)


@router.delete("/team/{member_id}")
def delete_team_member(member_id: int, session=Depends(get_current_session),
                       db: Session = Depends(get_db)):
    require_role(session, "owner")
    shop = session["shop"]
    sub = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.id == member_id,
        models.ShopSubUser.shop_id == shop.id
    ).first()
    if not sub:
        raise HTTPException(404, "Team member not found")
    db.delete(sub)
    db.commit()
    return {"deleted": True, "id": member_id}


# ── Sync ──────────────────────────────────────────────────────────────────────

@router.get("/sync")
def sync(session=Depends(get_current_session), db: Session = Depends(get_db),
         updated_since: str = Query(default=None)):
    shop = session["shop"]
    role = session["role"]
    prod_q = db.query(models.Product).filter(
        models.Product.shop_id == shop.id, models.Product.is_active == True)
    cat_q  = db.query(models.Category).filter(models.Category.shop_id == shop.id)
    if updated_since:
        try:
            dt = datetime.fromisoformat(updated_since)
            prod_q = prod_q.filter(models.Product.updated_at >= dt)
        except ValueError:
            pass
    return {
        "synced_at":  datetime.utcnow().isoformat(),
        "role":       role,
        "products":   [_product_json(p, role) for p in prod_q.all()],
        "categories": [_category_json(c) for c in cat_q.all()],
    }


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories")
def list_categories(session=Depends(get_current_session), db: Session = Depends(get_db)):
    shop = session["shop"]
    cats = db.query(models.Category).filter(
        models.Category.shop_id == shop.id).order_by(models.Category.name).all()
    return [_category_json(c) for c in cats]


@router.post("/categories", status_code=201)
def create_category(payload: dict, session=Depends(get_current_session),
                    db: Session = Depends(get_db)):
    require_role(session, "manager")
    shop = session["shop"]
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Category name is required")
    dup = db.query(models.Category).filter(
        models.Category.shop_id == shop.id,
        models.Category.name.ilike(name)).first()
    if dup:
        raise HTTPException(409, f"Category '{name}' already exists")
    cat = models.Category(shop_id=shop.id, name=name,
                          description=payload.get("description") or None,
                          color=payload.get("color", "#7c6af7"))
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return _category_json(cat)


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, session=Depends(get_current_session),
                    db: Session = Depends(get_db)):
    require_role(session, "manager")
    shop = session["shop"]
    cat = db.query(models.Category).filter(
        models.Category.id == category_id,
        models.Category.shop_id == shop.id).first()
    if not cat:
        raise HTTPException(404, "Category not found")
    db.query(models.Product).filter(
        models.Product.category_id == category_id
    ).update({"category_id": None})
    db.delete(cat)
    db.commit()
    return {"deleted": True, "id": category_id}


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
def list_products(session=Depends(get_current_session), db: Session = Depends(get_db),
                  search: str = "", category_id: int = None,
                  low_stock_only: bool = False, updated_since: str = Query(default=None)):
    shop = session["shop"]
    role = session["role"]
    q = db.query(models.Product).filter(
        models.Product.shop_id == shop.id, models.Product.is_active == True)
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))
    if category_id:
        q = q.filter(models.Product.category_id == category_id)
    if updated_since:
        try:
            q = q.filter(models.Product.updated_at >= datetime.fromisoformat(updated_since))
        except ValueError:
            pass
    prods = q.order_by(models.Product.name).all()
    if low_stock_only:
        prods = [p for p in prods if p.is_low_stock]
    return [_product_json(p, role) for p in prods]


@router.get("/products/barcode/{barcode}")
def product_by_barcode(barcode: str, session=Depends(get_current_session),
                       db: Session = Depends(get_db)):
    shop = session["shop"]
    role = session["role"]
    existing = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.sku == barcode,
        models.Product.is_active == True).first()
    if existing:
        return {"found_in_inventory": True, "product": _product_json(existing, role)}

    try:
        req = urllib.request.Request(
            f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json",
            headers={"User-Agent": "StockTracker-Mobile/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {"found_in_inventory": False, "off_data": None, "barcode": barcode}

    if data.get("status") != 1:
        return {"found_in_inventory": False, "off_data": None, "barcode": barcode}

    p     = data.get("product", {})
    name  = (p.get("product_name_en") or p.get("product_name") or "").strip()
    brand = p.get("brands", "").split(",")[0].strip()
    return {
        "found_in_inventory": False,
        "barcode": barcode,
        "off_data": {
            "name": f"{brand} {name}".strip() if brand and name else name or brand,
            "brand": brand,
            "description": p.get("quantity", ""),
            "image_url": p.get("image_front_small_url") or p.get("image_url") or "",
        }
    }


@router.post("/products", status_code=201)
def create_product(payload: dict, session=Depends(get_current_session),
                   db: Session = Depends(get_db)):
    require_role(session, "manager")
    shop = session["shop"]
    if not (payload.get("name") or "").strip():
        raise HTTPException(400, "Product name is required")
    cat_id = payload.get("category_id")
    product = models.Product(
        shop_id=shop.id, name=payload["name"].strip(),
        sku=payload.get("sku") or None,
        category_id=int(cat_id) if cat_id else None,
        description=payload.get("description") or None,
        unit=payload.get("unit", "pcs"),
        cost_price=float(payload.get("cost_price", 0)),
        selling_price=float(payload.get("selling_price", 0)),
        stock_quantity=float(payload.get("stock_quantity", 0)),
        low_stock_threshold=float(payload.get("low_stock_threshold", 10)),
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _product_json(product, session["role"])


# ── Transactions ──────────────────────────────────────────────────────────────

@router.get("/transactions")
def list_transactions(session=Depends(get_current_session), db: Session = Depends(get_db),
                      limit: int = 50, offset: int = 0,
                      txn_type: str = Query(default="", alias="type")):
    shop = session["shop"]
    q = db.query(models.Transaction).filter(models.Transaction.shop_id == shop.id)
    if txn_type in ("sale", "purchase", "adjustment"):
        q = q.filter(models.Transaction.transaction_type == models.TransactionType(txn_type))
    # Cashiers see only their own sales — all other roles see everything
    total = q.count()
    txns  = q.order_by(models.Transaction.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "offset": offset, "limit": limit,
            "items": [_transaction_json(t) for t in txns]}


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int, session=Depends(get_current_session),
                    db: Session = Depends(get_db)):
    shop = session["shop"]
    txn = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.shop_id == shop.id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return _transaction_json(txn, include_items=True)


@router.post("/transactions", status_code=201)
def create_transaction(payload: dict, session=Depends(get_current_session),
                       db: Session = Depends(get_db)):
    from datetime import date as _date
    shop       = session["shop"]
    role       = session["role"]
    txn_type   = payload.get("transaction_type", "sale")
    items_data = payload.get("items", [])
    tax_rate   = float(payload.get("tax_rate", 0.0))

    if role == "cashier" and txn_type != "sale":
        raise HTTPException(403, "Cashiers can only record sales")
    if not items_data:
        raise HTTPException(400, "At least one item is required")

    subtotal = 0.0
    resolved = []   # (product, qty, price, sub, expiry_date, lot_number)
    for item in items_data:
        product = db.query(models.Product).filter(
            models.Product.id == item["product_id"],
            models.Product.shop_id == shop.id,
            models.Product.is_active == True).first()
        if not product:
            raise HTTPException(404, f"Product {item['product_id']} not found")
        qty   = float(item["quantity"])
        price = float(item["unit_price"])
        sub   = qty * price
        subtotal += sub
        # Parse optional per-item expiry / lot (only used for purchases)
        exp_raw = item.get("expiry_date") or ""
        try:
            exp_date = _date.fromisoformat(exp_raw) if exp_raw else None
        except ValueError:
            exp_date = None
        lot = (item.get("lot_number") or "").strip() or None
        resolved.append((product, qty, price, sub, exp_date, lot))

    tax_amount   = round(subtotal * tax_rate / 100, 2)
    total_amount = round(subtotal + tax_amount, 2)

    txn = models.Transaction(
        shop_id=shop.id,
        transaction_type=models.TransactionType(txn_type),
        reference=payload.get("reference") or None,
        notes=payload.get("notes") or None,
        total_amount=total_amount,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
    )
    db.add(txn)
    db.flush()

    for product, qty, price, sub, exp_date, lot in resolved:
        if txn_type == "sale":
            # FEFO deduction — allocate from oldest-expiry batches first
            try:
                allocations = fefo.deduct_fefo(product, qty, db)
            except ValueError as e:
                db.rollback()
                raise HTTPException(400, str(e))
            # Create one TransactionItem per batch allocation
            for batch, taken in allocations:
                db.add(models.TransactionItem(
                    transaction_id=txn.id, product_id=product.id,
                    batch_id=batch.id if batch else None,
                    quantity=taken, unit_price=price,
                    subtotal=round(taken * price, 2),
                    lot_number=batch.lot_number if batch else None,
                ))
        elif txn_type == "purchase":
            # Create a new batch for this restock
            batch = fefo.create_batch(
                product, qty,
                expiry_date=exp_date or product.default_expiry_date,
                lot_number=lot, db=db,
            )
            db.add(models.TransactionItem(
                transaction_id=txn.id, product_id=product.id,
                batch_id=batch.id, quantity=qty, unit_price=price, subtotal=sub,
                lot_number=lot,
            ))
        elif txn_type == "adjustment":
            product.stock_quantity = qty
            db.add(models.TransactionItem(
                transaction_id=txn.id, product_id=product.id,
                quantity=qty, unit_price=price, subtotal=sub,
            ))

    db.commit()
    return {
        "id": txn.id, "transaction_type": txn_type,
        "subtotal": round(subtotal, 2),
        "tax_amount": tax_amount, "tax_rate": tax_rate,
        "total_amount": total_amount,
        "items_count": len(resolved),
        "created_at": txn.created_at.isoformat(),
    }





# ── Batches / FEFO ────────────────────────────────────────────────────────────

@router.get("/products/{product_id}/batches")
def list_batches(product_id: int, session=Depends(get_current_session),
                 db: Session = Depends(get_db)):
    shop = session["shop"]
    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
    ).first()
    if not product:
        raise HTTPException(404, "Product not found")
    batches = sorted(product.batches, key=lambda b: (
        b.expiry_date is None, b.expiry_date, b.id))
    return {
        "product_id": product_id,
        "product_name": product.name,
        "batches": [_batch_json(b) for b in batches],
        "expiry_status": product.expiry_status,
    }


@router.get("/expiry")
def expiry_report(session=Depends(get_current_session), db: Session = Depends(get_db)):
    """Full expiry report — expired + expiring soon batches."""
    shop = session["shop"]
    warnings = fefo.expiry_warnings(shop.id, db)
    result = []
    for group in (warnings["expired"], warnings["expiring_soon"]):
        for w in group:
            p = w["product"]
            for b in w["batches"]:
                result.append({
                    "product_id":   p.id,
                    "product_name": p.name,
                    "batch_id":     b.id,
                    "lot_number":   b.lot_number,
                    "quantity":     b.quantity,
                    "expiry_date":  b.expiry_date.isoformat() if b.expiry_date else None,
                    "days_until_expiry": b.days_until_expiry,
                    "status":       b.expiry_status,
                })
    return {"items": result, "warn_days": warnings["warn_days"]}


# ── Share token (public receipt link) ────────────────────────────────────────

@router.post("/transactions/{transaction_id}/share")
def generate_share_token(
    transaction_id: int,
    request: Request,
    session=Depends(get_current_session),
    db: Session = Depends(get_db),
):
    import secrets as _secrets
    shop = session["shop"]
    txn  = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.shop_id == shop.id,
    ).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if not txn.share_token:
        txn.share_token = _secrets.token_hex(24)
        db.commit()
    base_url = str(request.base_url).rstrip("/")
    return {"url": f"{base_url}/receipt/{txn.share_token}"}


# ── Bulk CSV import ───────────────────────────────────────────────────────────

@router.post("/products/import")
async def api_import_products(
    request: Request,
    session=Depends(get_current_session),
    db: Session = Depends(get_db),
):
    """
    Accept a multipart CSV upload or a JSON body with a 'csv' key (raw CSV text).
    Returns a preview list when ?commit=false (default), or commits and returns summary.
    """
    require_role(session, "manager")
    shop   = session["shop"]
    commit = request.query_params.get("commit", "false").lower() == "true"

    content_type = request.headers.get("content-type", "")
    if "multipart" in content_type:
        from fastapi import UploadFile
        form = await request.form()
        file = form.get("file")
        if file is None:
            raise HTTPException(400, "No file uploaded")
        raw  = await file.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
    else:
        body = await request.json()
        text = body.get("csv", "")
        if not text:
            raise HTTPException(400, "Provide CSV text in the \'csv\' field")

    on_duplicate = request.query_params.get("on_duplicate", "skip")

    from routers.import_csv import _parse_csv, _f
    rows, error = _parse_csv(text, shop, db, on_duplicate)
    if error:
        raise HTTPException(400, error)

    if not commit:
        return {
            "preview": rows,
            "counts": {
                "create": sum(1 for r in rows if r["status"] == "create"),
                "update": sum(1 for r in rows if r["status"] == "update"),
                "skip":   sum(1 for r in rows if r["status"] == "skip"),
                "error":  sum(1 for r in rows if r["status"] == "error"),
            }
        }

    # Commit
    cats = {c.name.lower(): c for c in
            db.query(models.Category).filter(
                models.Category.shop_id == shop.id).all()}
    created = updated = skipped = 0
    for row in rows:
        if row["status"] == "error" or row["status"] == "skip":
            skipped += 1
            continue
        name  = row["name"].strip()
        sku   = row.get("sku", "").strip() or None
        cat_n = row.get("category", "").strip()
        cat_id = None
        if cat_n:
            key = cat_n.lower()
            if key not in cats:
                nc = models.Category(shop_id=shop.id, name=cat_n)
                db.add(nc); db.flush()
                cats[key] = nc
            cat_id = cats[cat_n.lower()].id
        existing = None
        if sku:
            existing = db.query(models.Product).filter(
                models.Product.shop_id == shop.id,
                models.Product.sku == sku,
                models.Product.is_active == True).first()
        if not existing:
            existing = db.query(models.Product).filter(
                models.Product.shop_id == shop.id,
                models.Product.name.ilike(name),
                models.Product.is_active == True).first()
        if existing:
            if on_duplicate == "update":
                existing.name = name; existing.sku = sku
                existing.category_id = cat_id
                existing.cost_price = _f(row.get("cost_price"), existing.cost_price)
                existing.selling_price = _f(row.get("selling_price"), existing.selling_price)
                existing.stock_quantity = _f(row.get("stock_quantity"), existing.stock_quantity)
                updated += 1
            else:
                skipped += 1
        else:
            db.add(models.Product(
                shop_id=shop.id, name=name, sku=sku, category_id=cat_id,
                description=row.get("description") or None,
                unit=row.get("unit") or "pcs",
                cost_price=_f(row.get("cost_price"), 0),
                selling_price=_f(row.get("selling_price"), 0),
                stock_quantity=_f(row.get("stock_quantity"), 0),
                low_stock_threshold=_f(row.get("low_stock_threshold"), 10),
            ))
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}

# ── Label PDF (QR labels) ─────────────────────────────────────────────────────

@router.get("/labels")
def download_labels(
    session=Depends(get_current_session),
    db: Session = Depends(get_db),
    ids: str = Query(default=""),
):
    """
    Generate a PDF of 50x30mm QR labels for the given product IDs.
    Pass ?ids=1,2,3 (comma-separated).
    """
    shop = session["shop"]
    if not ids.strip():
        raise HTTPException(400, "Provide at least one product id via ?ids=1,2,3")

    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "ids must be comma-separated integers")

    products = db.query(models.Product).filter(
        models.Product.id.in_(id_list),
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
    ).order_by(models.Product.name).all()

    if not products:
        raise HTTPException(404, "No matching products found")

    from routers.labels import build_labels_pdf
    pdf_bytes = build_labels_pdf(products, shop.name)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="labels.pdf"'},
    )

# ── Receipt PDF ───────────────────────────────────────────────────────────────

@router.get("/transactions/{transaction_id}/receipt")
def download_receipt(transaction_id: int, session=Depends(get_current_session),
                     db: Session = Depends(get_db)):
    shop = session["shop"]
    txn = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.shop_id == shop.id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")

    pdf_bytes = _build_receipt_pdf(txn, shop)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="receipt_{transaction_id}.pdf"'}
    )


def _build_receipt_pdf(txn: models.Transaction, shop: models.Shop) -> bytes:
    W = 80   # receipt width in mm (thermal printer standard)

    class ReceiptPDF(FPDF):
        def header(self): pass
        def footer(self): pass

    pdf = ReceiptPDF(format=(W, 297))   # height auto-trims at end
    pdf.add_page()
    pdf.set_margins(6, 4, 6)
    pdf.set_auto_page_break(False)

    # ── Shop name / logo placeholder ─────────────────────────────────────────
    pdf.set_fill_color(15, 17, 23)
    pdf.rect(0, 0, W, 24, 'F')
    pdf.set_y(5)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(245, 166, 35)
    pdf.cell(0, 7, shop.name.upper(), align="C", ln=True)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(120, 128, 160)
    pdf.cell(0, 5, "RECEIPT", align="C", ln=True)
    pdf.set_text_color(30, 30, 30)

    pdf.ln(4)

    # ── Transaction meta ──────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 8)
    date_str  = txn.created_at.strftime("%d %b %Y  %H:%M") if txn.created_at else "—"
    type_str  = txn.transaction_type.value.upper()
    pdf.set_fill_color(240, 240, 245)
    pdf.rect(6, pdf.get_y(), W - 12, 14, 'F')
    pdf.cell(0, 5, f"  Transaction #{txn.id}   {type_str}", ln=True)
    pdf.cell(0, 5, f"  Date: {date_str}", ln=True)
    if txn.reference:
        pdf.cell(0, 4, f"  Ref: {txn.reference}", ln=True)

    pdf.ln(3)
    # ── Line separator ────────────────────────────────────────────────────────
    pdf.set_draw_color(200, 200, 210)
    pdf.set_line_width(0.2)
    pdf.line(6, pdf.get_y(), W - 6, pdf.get_y())
    pdf.ln(2)

    # ── Items table ───────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(120, 128, 160)
    col = [38, 10, 13, 13]   # name, qty, price, subtotal
    pdf.cell(col[0], 5, "ITEM",     ln=False)
    pdf.cell(col[1], 5, "QTY",      align="C", ln=False)
    pdf.cell(col[2], 5, "PRICE",    align="R", ln=False)
    pdf.cell(col[3], 5, "SUBTOTAL", align="R", ln=True)
    pdf.line(6, pdf.get_y(), W - 6, pdf.get_y())
    pdf.ln(1)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(30, 30, 30)
    for item in txn.items:
        name = item.product.name if item.product else f"Product #{item.product_id}"
        # Wrap long names
        if len(name) > 22:
            name = name[:21] + "…"
        pdf.cell(col[0], 5, name, ln=False)
        pdf.cell(col[1], 5, str(int(item.quantity)) if item.quantity == int(item.quantity)
                 else f"{item.quantity:.1f}", align="C", ln=False)
        pdf.cell(col[2], 5, f"${item.unit_price:.2f}", align="R", ln=False)
        pdf.cell(col[3], 5, f"${item.subtotal:.2f}",   align="R", ln=True)
        if item.lot_number:
            pdf.set_font("Courier", "", 5)
            pdf.set_text_color(150, 150, 165)
            pdf.cell(sum(col), 3.5, f"  Lot: {item.lot_number}", ln=True)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(30, 30, 30)

    pdf.ln(2)
    pdf.line(6, pdf.get_y(), W - 6, pdf.get_y())
    pdf.ln(2)

    # ── Totals ────────────────────────────────────────────────────────────────
    subtotal = txn.total_amount - txn.tax_amount
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(55, 5, "Subtotal:", align="R", ln=False)
    pdf.cell(13, 5, f"${subtotal:.2f}", align="R", ln=True)
    if txn.tax_rate and txn.tax_rate > 0:
        pdf.cell(55, 5, f"Tax ({txn.tax_rate:.1f}%):", align="R", ln=False)
        pdf.cell(13, 5, f"${txn.tax_amount:.2f}", align="R", ln=True)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(245, 166, 35)
    pdf.set_text_color(0, 0, 0)
    y = pdf.get_y()
    pdf.rect(6, y, W - 12, 8, 'F')
    pdf.set_y(y + 1)
    pdf.cell(55, 6, "TOTAL:", align="R", ln=False)
    pdf.cell(13, 6, f"${txn.total_amount:.2f}", align="R", ln=True)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(4)

    # ── QR code ───────────────────────────────────────────────────────────────
    qr_data = f"STOCKTRACKER:TXN:{txn.id}:SHOP:{txn.shop_id}"
    qr_img  = qrcode.make(qr_data, box_size=3, border=2)
    qr_buf  = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_x = (W - 28) / 2
    pdf.image(qr_buf, x=qr_x, y=pdf.get_y(), w=28)
    pdf.ln(30)
    pdf.set_font("Helvetica", "", 6)
    pdf.set_text_color(150, 150, 160)
    pdf.cell(0, 4, f"TXN #{txn.id} — Scan to verify", align="C", ln=True)
    pdf.ln(3)

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.line(6, pdf.get_y(), W - 6, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(80, 80, 90)
    pdf.cell(0, 5, "Thank you for your business!", align="C", ln=True)
    pdf.set_font("Helvetica", "", 6)
    pdf.cell(0, 4, shop.name, align="C", ln=True)
    pdf.ln(2)

    return bytes(pdf.output())


def _batch_json(b: models.ProductBatch) -> dict:
    return {
        "id":          b.id,
        "lot_number":  b.lot_number,
        "quantity":    b.quantity,
        "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
        "expiry_status": b.expiry_status,
        "days_until_expiry": b.days_until_expiry,
        "received_at": b.received_at.isoformat() if b.received_at else None,
        "notes":       b.notes,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _product_json(p: models.Product, role: str = "owner") -> dict:
    earliest = p.earliest_expiry
    data = {
        "id": p.id, "name": p.name, "sku": p.sku,
        "description": p.description, "unit": p.unit,
        "selling_price": p.selling_price,
        "stock_quantity": p.stock_quantity,
        "low_stock_threshold": p.low_stock_threshold,
        "is_low_stock": p.is_low_stock,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "expiry_status":    p.expiry_status,
        "earliest_expiry":  earliest.isoformat() if earliest else None,
        "default_expiry_date": p.default_expiry_date.isoformat() if p.default_expiry_date else None,
        "category": {"id": p.category_obj.id, "name": p.category_obj.name,
                     "color": p.category_obj.color} if p.category_obj else None,
    }
    # Cost price and stock value hidden from cashiers
    if _role_level(role) >= _role_level("manager"):
        data["cost_price"]  = p.cost_price
        data["stock_value"] = round(p.stock_value, 2)
    return data


def _category_json(c: models.Category) -> dict:
    return {"id": c.id, "name": c.name, "description": c.description,
            "color": c.color, "product_count": c.product_count}


def _transaction_json(t: models.Transaction, include_items: bool = False) -> dict:
    data = {
        "id": t.id,
        "transaction_type": t.transaction_type.value,
        "reference": t.reference,
        "notes": t.notes,
        "subtotal": round(t.total_amount - t.tax_amount, 2),
        "tax_amount": round(t.tax_amount, 2),
        "tax_rate": t.tax_rate,
        "total_amount": round(t.total_amount, 2),
        "items_count": len(t.items),
        "created_at": t.created_at.isoformat(),
    }
    if include_items:
        data["items"] = [{
            "product_id":   i.product_id,
            "product_name": i.product.name if i.product else "—",
            "quantity":     i.quantity,
            "unit_price":   i.unit_price,
            "subtotal":     i.subtotal,
            "unit":         i.product.unit if i.product else "pcs",
            "lot_number":   i.lot_number,
            "batch_id":     i.batch_id,
        } for i in t.items]
    return data


def _sub_user_json(s: models.ShopSubUser) -> dict:
    return {"id": s.id, "name": s.name, "username": s.username,
            "role": s.role.value, "is_active": s.is_active,
            "created_at": s.created_at.isoformat()}
