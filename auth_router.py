from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import ValidationError
from database import get_db
import models, auth, schemas

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("shop_id"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("shop_id"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    shop = db.query(models.Shop).filter(models.Shop.username == username).first()
    if not shop or not auth.verify_password(password, shop.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    auth.login_shop(request, shop)
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    shop_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(default=None),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Validate with Pydantic
    try:
        validated = schemas.RegisterRequest(
            shop_name=shop_name,
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_password
        )
    except ValidationError as e:
        error_msg = e.errors()[0]['msg'] if e.errors() else "Validation error"
        return templates.TemplateResponse("register.html", {
            "request": request, "error": error_msg
        })
    
    existing = db.query(models.Shop).filter(models.Shop.username == validated.username).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Username already taken"
        })
    shop = models.Shop(
        name=validated.shop_name,
        username=validated.username,
        email=validated.email,
        password_hash=auth.hash_password(validated.password)
    )
    db.add(shop)
    db.commit()
    db.refresh(shop)
    auth.login_shop(request, shop)
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    auth.logout_shop(request)
    return RedirectResponse(url="/login", status_code=302)
