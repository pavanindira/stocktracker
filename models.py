from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    Boolean, Text, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from database import Base


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    products = relationship("Product", back_populates="shop", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="shop", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    name = Column(String(200), nullable=False)
    sku = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    unit = Column(String(50), default="pcs")
    cost_price = Column(Float, default=0.0)
    selling_price = Column(Float, default=0.0)
    stock_quantity = Column(Float, default=0.0)
    low_stock_threshold = Column(Float, default=10.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    shop = relationship("Shop", back_populates="products")
    transactions = relationship("TransactionItem", back_populates="product")

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def stock_value(self):
        return self.stock_quantity * self.cost_price


class TransactionType(str, enum.Enum):
    PURCHASE = "purchase"   # stock coming in
    SALE = "sale"           # stock going out
    ADJUSTMENT = "adjustment"  # manual correction


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    total_amount = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    shop = relationship("Shop", back_populates="transactions")
    items = relationship("TransactionItem", back_populates="transaction", cascade="all, delete-orphan")


class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    transaction = relationship("Transaction", back_populates="items")
    product = relationship("Product", back_populates="transactions")
