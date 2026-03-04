from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return RedirectResponse(url="/login", status_code=302)
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if shop and shop.is_admin:
        return RedirectResponse(url="/admin", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    shop_id = request.session.get("shop_id")
    if shop_id:
        shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
        if shop and shop.is_admin:
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    def fail(msg):
        return templates.TemplateResponse("login.html",
                                          {"request": request, "error": msg})

    # 1. Check owner/admin accounts
    shop = db.query(models.Shop).filter(models.Shop.username == username).first()
    if shop:
        if not auth.verify_password(password, shop.password_hash):
            return fail("Invalid username or password")
        if not shop.is_active:
            return fail("This account has been deactivated.")
        auth.login_shop(request, shop)
        return RedirectResponse(url="/admin" if shop.is_admin else "/dashboard",
                                status_code=302)

    # 2. Check sub-users (cashier / manager)
    sub = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.username == username
    ).first()
    if sub:
        if not auth.verify_password(password, sub.password_hash):
            return fail("Invalid username or password")
        if not sub.is_active:
            return fail("This account has been deactivated.")
        owner = db.query(models.Shop).filter(models.Shop.id == sub.shop_id).first()
        if not owner or not owner.is_active:
            return fail("The shop account is inactive.")
        auth.login_sub_user(request, sub, owner)
        return RedirectResponse(url="/dashboard", status_code=302)

    return fail("Invalid username or password")


@router.get("/logout")
async def logout(request: Request):
    auth.logout_shop(request)
    return RedirectResponse(url="/login", status_code=302)
