"""
Team management — owner creates/manages cashier and manager sub-accounts.
All routes require role = owner.
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth

router = APIRouter(prefix="/team")
templates = Jinja2Templates(directory="templates")


def _get_shop_and_assert_owner(request: Request, db: Session):
    shop = auth.get_session_shop(request, db)
    if not shop:
        return None, RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "owner"):
        return None, RedirectResponse(url="/dashboard", status_code=302)
    return shop, None


@router.get("", response_class=HTMLResponse)
async def team_list(request: Request, db: Session = Depends(get_db)):
    shop, redir = _get_shop_and_assert_owner(request, db)
    if redir:
        return redir
    members = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.shop_id == shop.id
    ).order_by(models.ShopSubUser.created_at).all()
    return templates.TemplateResponse("team/index.html", {
        "request": request, "shop": shop, "members": members
    })


@router.get("/new", response_class=HTMLResponse)
async def team_new(request: Request, db: Session = Depends(get_db)):
    shop, redir = _get_shop_and_assert_owner(request, db)
    if redir:
        return redir
    return templates.TemplateResponse("team/form.html", {
        "request": request, "shop": shop, "member": None, "error": None
    })


@router.post("/new", response_class=HTMLResponse)
async def team_create(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    shop, redir = _get_shop_and_assert_owner(request, db)
    if redir:
        return redir

    def fail(msg):
        return templates.TemplateResponse("team/form.html", {
            "request": request, "shop": shop, "member": None, "error": msg,
            "form": {"name": name, "username": username, "role": role}
        })

    # Unique username check across shops AND sub_users
    taken_shop = db.query(models.Shop).filter(models.Shop.username == username).first()
    taken_sub  = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.username == username).first()
    if taken_shop or taken_sub:
        return fail(f"Username '{username}' is already taken.")

    if role not in ("manager", "cashier"):
        return fail("Invalid role selected.")

    if len(password) < 8:
        return fail("Password must be at least 8 characters.")

    sub = models.ShopSubUser(
        shop_id=shop.id,
        name=name.strip(),
        username=username.strip(),
        password_hash=auth.hash_password(password),
        role=models.UserRole(role),
    )
    db.add(sub)
    db.commit()
    return RedirectResponse(url="/team", status_code=302)


@router.get("/{member_id}/edit", response_class=HTMLResponse)
async def team_edit(request: Request, member_id: int, db: Session = Depends(get_db)):
    shop, redir = _get_shop_and_assert_owner(request, db)
    if redir:
        return redir
    member = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.id == member_id,
        models.ShopSubUser.shop_id == shop.id
    ).first()
    if not member:
        return RedirectResponse(url="/team", status_code=302)
    return templates.TemplateResponse("team/form.html", {
        "request": request, "shop": shop, "member": member, "error": None
    })


@router.post("/{member_id}/edit", response_class=HTMLResponse)
async def team_update(
    request: Request,
    member_id: int,
    name: str = Form(...),
    role: str = Form(...),
    new_password: str = Form(default=""),
    is_active: str = Form(default=""),
    db: Session = Depends(get_db)
):
    shop, redir = _get_shop_and_assert_owner(request, db)
    if redir:
        return redir
    member = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.id == member_id,
        models.ShopSubUser.shop_id == shop.id
    ).first()
    if not member:
        return RedirectResponse(url="/team", status_code=302)

    member.name      = name.strip()
    member.role      = models.UserRole(role)
    member.is_active = (is_active == "on")
    if new_password:
        if len(new_password) < 8:
            return templates.TemplateResponse("team/form.html", {
                "request": request, "shop": shop, "member": member,
                "error": "Password must be at least 8 characters."
            })
        member.password_hash = auth.hash_password(new_password)
    db.commit()
    return RedirectResponse(url="/team", status_code=302)


@router.post("/{member_id}/delete")
async def team_delete(request: Request, member_id: int, db: Session = Depends(get_db)):
    shop, redir = _get_shop_and_assert_owner(request, db)
    if redir:
        return redir
    member = db.query(models.ShopSubUser).filter(
        models.ShopSubUser.id == member_id,
        models.ShopSubUser.shop_id == shop.id
    ).first()
    if member:
        db.delete(member)
        db.commit()
    return RedirectResponse(url="/team", status_code=302)
