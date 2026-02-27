from passlib.context import CryptContext
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_current_shop(request: Request, db: Session) -> models.Shop:
    shop_id = request.session.get("shop_id")
    if not shop_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=401, detail="Shop not found")
    return shop


def login_shop(request: Request, shop: models.Shop):
    request.session["shop_id"] = shop.id
    request.session["shop_name"] = shop.name


def logout_shop(request: Request):
    request.session.clear()
