"""
fefo.py — First-Expiry First-Out stock movement engine.

Public API:
  deduct_fefo(product, qty, db)  → list of (batch, qty_taken) pairs
  create_batch(product, qty, expiry_date, lot_number, db) → ProductBatch
  expiry_warnings(shop_id, db)   → dict with 'expired' and 'soon' product lists
"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
import models


WARN_DAYS = models.EXPIRY_WARN_DAYS


# ── Batch creation (on purchase / restock) ────────────────────────────────────

def create_batch(
    product: models.Product,
    quantity: float,
    expiry_date: date | None,
    lot_number: str | None,
    db: Session,
    notes: str | None = None,
) -> models.ProductBatch:
    """
    Create a new ProductBatch and increment the product's stock_quantity.
    Returns the created batch.
    """
    batch = models.ProductBatch(
        product_id  = product.id,
        lot_number  = lot_number or None,
        quantity    = quantity,
        expiry_date = expiry_date,
        notes       = notes,
    )
    db.add(batch)
    product.stock_quantity += quantity
    db.flush()
    return batch


# ── FEFO deduction (on sale) ──────────────────────────────────────────────────

def deduct_fefo(
    product: models.Product,
    qty_needed: float,
    db: Session,
) -> list[tuple[models.ProductBatch | None, float]]:
    """
    Deduct `qty_needed` units from the product's batches in FEFO order
    (earliest expiry_date first; batches without expiry last).

    Returns a list of (batch_or_None, qty_taken) tuples — used to set
    batch_id / lot_number on TransactionItem rows.

    Also decrements product.stock_quantity.
    Raises ValueError if total available stock < qty_needed.
    """
    # Sort: expiring batches first (None expiry last), then by received_at
    active = sorted(
        [b for b in product.batches if b.quantity > 0],
        key=lambda b: (b.expiry_date is None, b.expiry_date or date.max, b.id),
    )

    total_available = sum(b.quantity for b in active)
    if total_available < qty_needed:
        raise ValueError(
            f"Insufficient stock for '{product.name}': "
            f"need {qty_needed}, have {total_available}"
        )

    allocations: list[tuple[models.ProductBatch | None, float]] = []
    remaining = qty_needed

    for batch in active:
        if remaining <= 0:
            break
        take = min(batch.quantity, remaining)
        batch.quantity -= take
        remaining      -= take
        allocations.append((batch, take))

    # If stock isn't tracked in batches at all (legacy products with no batches),
    # fall back to a single allocation with no batch reference.
    if not allocations and product.stock_quantity >= qty_needed:
        allocations.append((None, qty_needed))

    product.stock_quantity -= qty_needed
    return allocations


# ── Expiry dashboard data ─────────────────────────────────────────────────────

def expiry_warnings(shop_id: int, db: Session) -> dict:
    """
    Return dicts of products and batches that are expired or expiring soon.
    Used by the dashboard widget and the expiry report.
    """
    today = date.today()
    warn  = today + timedelta(days=WARN_DAYS)

    products = db.query(models.Product).filter(
        models.Product.shop_id == shop_id,
        models.Product.is_active == True,
        models.Product.stock_quantity > 0,
    ).all()

    expired      = []   # product has at least one expired active batch
    expiring_soon = []  # product has at least one batch expiring within WARN_DAYS

    for p in products:
        active_batches = [b for b in p.batches if b.quantity > 0]
        exp_b   = [b for b in active_batches if b.expiry_date and b.expiry_date < today]
        soon_b  = [b for b in active_batches
                   if b.expiry_date and today <= b.expiry_date <= warn]

        # Also check product-level default_expiry_date if no batches
        if not active_batches and p.default_expiry_date:
            if p.default_expiry_date < today:
                exp_b = [_fake_batch(p)]
            elif p.default_expiry_date <= warn:
                soon_b = [_fake_batch(p)]

        if exp_b:
            expired.append({"product": p, "batches": exp_b})
        elif soon_b:
            expiring_soon.append({"product": p, "batches": soon_b})

    # Sort: most urgent first
    expired.sort(key=lambda x: min(
        (b.expiry_date for b in x["batches"] if b.expiry_date),
        default=date.min))
    expiring_soon.sort(key=lambda x: min(
        (b.expiry_date for b in x["batches"] if b.expiry_date),
        default=date.max))

    return {
        "expired":       expired,
        "expiring_soon": expiring_soon,
        "warn_days":     WARN_DAYS,
        "today":         today,
    }


class _fake_batch:
    """Minimal batch-like object for products without batch records."""
    def __init__(self, product: models.Product):
        self.lot_number  = None
        self.quantity    = product.stock_quantity
        self.expiry_date = product.default_expiry_date
        self.id          = None
