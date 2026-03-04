from passlib.context import CryptContext
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
import models

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Role hierarchy: higher number = more permissions
_ROLE_LEVEL = {
    models.UserRole.CASHIER: 1,
    models.UserRole.MANAGER: 2,
    models.UserRole.OWNER:   3,
    "cashier": 1, "manager": 2, "owner": 3,   # also accept raw strings
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Session helpers ───────────────────────────────────────────────────────────

def login_shop(request: Request, shop: models.Shop):
    """Log in the owner account (role = owner)."""
    request.session["shop_id"]     = shop.id
    request.session["shop_name"]   = shop.name
    request.session["is_admin"]    = shop.is_admin
    request.session["role"]        = "owner"
    request.session["sub_user_id"] = None


def login_sub_user(request: Request, sub: models.ShopSubUser, shop: models.Shop):
    """Log in a cashier or manager sub-account."""
    request.session["shop_id"]     = shop.id
    request.session["shop_name"]   = shop.name
    request.session["is_admin"]    = False
    request.session["role"]        = sub.role.value
    request.session["sub_user_id"] = sub.id
    request.session["user_name"]   = sub.name


def logout_shop(request: Request):
    request.session.clear()


def get_session_role(request: Request) -> str:
    return request.session.get("role", "owner")


def has_role(request: Request, min_role: str) -> bool:
    """Return True if the current user's role is >= min_role."""
    current = get_session_role(request)
    return _ROLE_LEVEL.get(current, 3) >= _ROLE_LEVEL.get(min_role, 1)


def require_min_role(request: Request, min_role: str):
    """Raise 403 if the current user's role is below min_role."""
    if not has_role(request, min_role):
        raise HTTPException(status_code=403,
                            detail=f"Your role does not allow this action.")


# ── Shop / admin guards ───────────────────────────────────────────────────────

def get_session_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


def get_current_shop(request: Request, db: Session) -> models.Shop:
    shop = get_session_shop(request, db)
    if not shop:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return shop


def require_admin(request: Request, db: Session) -> models.Shop:
    shop = get_session_shop(request, db)
    if not shop or not shop.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return shop
