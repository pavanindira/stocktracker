from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    Boolean, Text, Enum, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import date, timedelta
import enum
from database import Base

EXPIRY_WARN_DAYS = 30   # "expiring soon" threshold


class UserRole(str, enum.Enum):
    OWNER   = "owner"
    MANAGER = "manager"
    CASHIER = "cashier"


class Shop(Base):
    __tablename__ = "shops"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100), nullable=False)
    username      = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    email         = Column(String(100), unique=True, nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    is_active     = Column(Boolean, default=True)
    is_admin      = Column(Boolean, default=False)

    categories   = relationship("Category",    back_populates="shop", cascade="all, delete-orphan")
    products     = relationship("Product",     back_populates="shop", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="shop", cascade="all, delete-orphan")
    sub_users    = relationship("ShopSubUser", back_populates="shop", cascade="all, delete-orphan")
    suppliers    = relationship("Supplier",    back_populates="shop",    cascade="all, delete-orphan")


class ShopSubUser(Base):
    __tablename__ = "shop_sub_users"

    id            = Column(Integer, primary_key=True, index=True)
    shop_id       = Column(Integer, ForeignKey("shops.id"), nullable=False)
    name          = Column(String(200), nullable=False)
    username      = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    role          = Column(Enum(UserRole), nullable=False, default=UserRole.CASHIER)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    shop = relationship("Shop", back_populates="sub_users")


class Category(Base):
    __tablename__ = "categories"

    id          = Column(Integer, primary_key=True, index=True)
    shop_id     = Column(Integer, ForeignKey("shops.id"), nullable=False)
    name        = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    color       = Column(String(7), default="#7c6af7")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    shop     = relationship("Shop", back_populates="categories")
    products = relationship("Product", back_populates="category_obj")

    @property
    def product_count(self):
        return len([p for p in self.products if p.is_active])


class Product(Base):
    __tablename__ = "products"

    id                  = Column(Integer, primary_key=True, index=True)
    shop_id             = Column(Integer, ForeignKey("shops.id"), nullable=False)
    category_id         = Column(Integer, ForeignKey("categories.id"), nullable=True)
    name                = Column(String(200), nullable=False)
    sku                 = Column(String(100), nullable=True)
    description         = Column(Text, nullable=True)
    unit                = Column(String(50), default="pcs")
    cost_price          = Column(Float, default=0.0)
    selling_price       = Column(Float, default=0.0)
    stock_quantity      = Column(Float, default=0.0)
    low_stock_threshold = Column(Float, default=10.0)
    default_expiry_date = Column(Date, nullable=True)   # product-level default expiry
    supplier_id         = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    reorder_quantity    = Column(Float, default=0.0)        # suggested reorder qty
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())
    is_active           = Column(Boolean, default=True)

    shop         = relationship("Shop",            back_populates="products")
    supplier     = relationship("Supplier",        back_populates="products",
                                foreign_keys="[Product.supplier_id]")
    category_obj = relationship("Category",        back_populates="products")
    transactions = relationship("TransactionItem", back_populates="product")
    batches      = relationship("ProductBatch",    back_populates="product",
                                cascade="all, delete-orphan",
                                order_by="ProductBatch.expiry_date")

    @property
    def category_name(self):
        return self.category_obj.name if self.category_obj else "—"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def stock_value(self):
        return self.stock_quantity * self.cost_price

    # ── Expiry helpers ────────────────────────────────────────────────────────
    @property
    def earliest_expiry(self) -> date | None:
        """Earliest expiry date across all active batches (FEFO front)."""
        active = [b for b in self.batches if b.quantity > 0 and b.expiry_date]
        if active:
            return min(b.expiry_date for b in active)
        return self.default_expiry_date

    @property
    def expiry_status(self) -> str:
        """'expired' | 'soon' | 'ok' | 'none'"""
        exp = self.earliest_expiry
        if exp is None:
            return "none"
        today = date.today()
        if exp < today:
            return "expired"
        if exp <= today + timedelta(days=EXPIRY_WARN_DAYS):
            return "soon"
        return "ok"

    @property
    def has_expired_batches(self) -> bool:
        today = date.today()
        return any(b.expiry_date and b.expiry_date < today and b.quantity > 0
                   for b in self.batches)

    @property
    def has_expiring_soon_batches(self) -> bool:
        today = date.today()
        warn  = today + timedelta(days=EXPIRY_WARN_DAYS)
        return any(b.expiry_date and today <= b.expiry_date <= warn and b.quantity > 0
                   for b in self.batches)


class ProductBatch(Base):
    """
    A batch/lot of stock with its own expiry date and quantity.
    Created when a purchase (restock) transaction is recorded.
    FEFO: batches sorted by expiry_date ASC — oldest expiry sold first.
    """
    __tablename__ = "product_batches"

    id             = Column(Integer, primary_key=True, index=True)
    product_id     = Column(Integer, ForeignKey("products.id"), nullable=False)
    lot_number     = Column(String(100), nullable=True)   # optional lot/batch code
    quantity       = Column(Float, nullable=False, default=0.0)
    expiry_date    = Column(Date, nullable=True)
    received_at    = Column(DateTime(timezone=True), server_default=func.now())
    notes          = Column(Text, nullable=True)

    product = relationship("Product", back_populates="batches")

    @property
    def expiry_status(self) -> str:
        if not self.expiry_date:
            return "none"
        today = date.today()
        if self.expiry_date < today:
            return "expired"
        if self.expiry_date <= today + timedelta(days=EXPIRY_WARN_DAYS):
            return "soon"
        return "ok"

    @property
    def days_until_expiry(self) -> int | None:
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days


class TransactionType(str, enum.Enum):
    PURCHASE   = "purchase"
    SALE       = "sale"
    ADJUSTMENT = "adjustment"


class Transaction(Base):
    __tablename__ = "transactions"

    id               = Column(Integer, primary_key=True, index=True)
    shop_id          = Column(Integer, ForeignKey("shops.id"), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    reference        = Column(String(100), nullable=True)
    notes            = Column(Text, nullable=True)
    total_amount     = Column(Float, default=0.0)
    tax_amount       = Column(Float, default=0.0)
    tax_rate         = Column(Float, default=0.0)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    share_token      = Column(String(64), unique=True, nullable=True, index=True)
    supplier_id      = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    shop     = relationship("Shop",     back_populates="transactions")
    supplier = relationship("Supplier",  back_populates="transactions",
                             foreign_keys="[Transaction.supplier_id]")
    items = relationship("TransactionItem", back_populates="transaction",
                         cascade="all, delete-orphan")


class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id             = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    product_id     = Column(Integer, ForeignKey("products.id"), nullable=False)
    batch_id       = Column(Integer, ForeignKey("product_batches.id"), nullable=True)
    quantity       = Column(Float, nullable=False)
    unit_price     = Column(Float, nullable=False)
    subtotal       = Column(Float, nullable=False)
    lot_number     = Column(String(100), nullable=True)   # snapshot at sale time

    transaction = relationship("Transaction",   back_populates="items")
    product     = relationship("Product",       back_populates="transactions")
    batch       = relationship("ProductBatch")


# ═══════════════════════════════════════════════════════════════════════════════
# Supplier management
# ═══════════════════════════════════════════════════════════════════════════════

class Supplier(Base):
    __tablename__ = "suppliers"

    id              = Column(Integer, primary_key=True, index=True)
    shop_id         = Column(Integer, ForeignKey("shops.id"), nullable=False)
    name            = Column(String(200), nullable=False)
    contact_name    = Column(String(200), nullable=True)
    phone           = Column(String(50),  nullable=True)
    email           = Column(String(200), nullable=True)
    website         = Column(String(300), nullable=True)
    notes           = Column(Text,        nullable=True)
    lead_time_days  = Column(Integer,     default=3)    # typical days from order to delivery
    is_active       = Column(Boolean,     default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    shop          = relationship("Shop")
    products      = relationship("Product",     back_populates="supplier",
                                 foreign_keys="Product.supplier_id")
    transactions  = relationship("Transaction", back_populates="supplier",
                                 foreign_keys="Transaction.supplier_id")

    @property
    def product_count(self):
        return len([p for p in self.products if p.is_active])

    @property
    def reorder_count(self):
        return len([p for p in self.products
                    if p.is_active and p.is_low_stock])


# ═══════════════════════════════════════════════════════════════════════════════
# Stocktake
# ═══════════════════════════════════════════════════════════════════════════════

class StocktakeStatus(str, enum.Enum):
    DRAFT       = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"


class Stocktake(Base):
    __tablename__ = "stocktakes"

    id           = Column(Integer, primary_key=True, index=True)
    shop_id      = Column(Integer, ForeignKey("shops.id"), nullable=False)
    name         = Column(String(200), nullable=False)
    status       = Column(Enum(StocktakeStatus), default=StocktakeStatus.DRAFT)
    notes        = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    shop  = relationship("Shop")
    items = relationship("StocktakeItem", back_populates="stocktake",
                         cascade="all, delete-orphan")

    @property
    def items_counted(self):
        return len([i for i in self.items if i.counted_quantity is not None])

    @property
    def total_items(self):
        return len(self.items)

    @property
    def variance_count(self):
        return len([i for i in self.items
                    if i.counted_quantity is not None and i.variance != 0])


class StocktakeItem(Base):
    __tablename__ = "stocktake_items"

    id               = Column(Integer, primary_key=True, index=True)
    stocktake_id     = Column(Integer, ForeignKey("stocktakes.id"), nullable=False)
    product_id       = Column(Integer, ForeignKey("products.id"),   nullable=False)
    system_quantity  = Column(Float, nullable=False)          # snapshot at stocktake creation
    counted_quantity = Column(Float, nullable=True)           # entered by user; None = not yet counted
    notes            = Column(Text, nullable=True)

    stocktake = relationship("Stocktake", back_populates="items")
    product   = relationship("Product")

    @property
    def variance(self) -> float:
        if self.counted_quantity is None:
            return 0.0
        return self.counted_quantity - self.system_quantity

    @property
    def variance_pct(self) -> float | None:
        if self.system_quantity == 0:
            return None
        return self.variance / self.system_quantity * 100
