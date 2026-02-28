from pydantic import BaseModel, Field, validator
from typing import Optional
from enum import Enum


class TransactionTypeEnum(str, Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    ADJUSTMENT = "adjustment"


# Auth schemas
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    shop_name: str = Field(..., min_length=1, max_length=100)
    username: str = Field(..., min_length=1, max_length=50)
    email: Optional[str] = Field(None, max_length=100)
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=1)

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v

    @validator('username')
    def username_alphanumeric(cls, v):
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores')
        return v


# Product schemas
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    sku: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    unit: str = Field(default="pcs", max_length=50)
    cost_price: float = Field(..., ge=0)
    selling_price: float = Field(..., ge=0)
    stock_quantity: float = Field(default=0, ge=0)
    low_stock_threshold: float = Field(default=10, ge=0)


class ProductUpdate(ProductCreate):
    pass


# Transaction schemas
class TransactionItemRequest(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)


class TransactionCreate(BaseModel):
    transaction_type: TransactionTypeEnum
    reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    product_ids: list[int]
    quantities: list[float]
    unit_prices: list[float]

    @validator('quantities', each_item=True)
    def quantity_positive(cls, v):
        if v <= 0:
            raise ValueError('Quantity must be positive')
        return v

    @validator('unit_prices', each_item=True)
    def price_non_negative(cls, v):
        if v < 0:
            raise ValueError('Price cannot be negative')
        return v

    @validator('product_ids')
    def validate_product_ids(cls, v):
        if not v:
            raise ValueError('At least one product is required')
        return v
