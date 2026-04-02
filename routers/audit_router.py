"""
Audit log routes.
  GET /audit   — paginated log with action / entity / actor filters
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth

router    = APIRouter(prefix="/audit")
templates = Jinja2Templates(directory="templates")


def _shop(request, db):
    sid = request.session.get("shop_id")
    return db.query(models.Shop).filter(models.Shop.id == sid).first() if sid else None


@router.get("", response_class=HTMLResponse)
async def audit_log(
    request: Request,
    action: str = "",
    actor: str  = "",
    page: int   = 1,
    db: Session = Depends(get_db),
):
    shop = _shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)
    if not auth.has_role(request, "manager"):
        return RedirectResponse(url="/dashboard", status_code=302)

    PER_PAGE = 50
    q = db.query(models.AuditLog).filter(models.AuditLog.shop_id == shop.id)
    if action:
        # Escape LIKE wildcards
        esc = action.replace('%', r'\%').replace('_', r'\_')
        q = q.filter(models.AuditLog.action.ilike(f"%{esc}%", escape='\\'))
    if actor:
        esc = actor.replace('%', r'\%').replace('_', r'\_')
        q = q.filter(models.AuditLog.actor_name.ilike(f"%{esc}%", escape='\\'))

    total  = q.count()
    logs   = q.order_by(models.AuditLog.created_at.desc()) \
              .offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    pages  = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    # Distinct values for filter dropdowns
    actions = [r[0] for r in db.query(models.AuditLog.action)
               .filter(models.AuditLog.shop_id == shop.id)
               .distinct().order_by(models.AuditLog.action).all()]
    actors  = [r[0] for r in db.query(models.AuditLog.actor_name)
               .filter(models.AuditLog.shop_id == shop.id)
               .distinct().order_by(models.AuditLog.actor_name).all()]

    return templates.TemplateResponse("audit/index.html", {
        "request": request, "shop": shop,
        "logs": logs, "total": total,
        "page": page, "pages": pages,
        "filter_action": action, "filter_actor": actor,
        "actions": actions, "actors": actors,
    })
