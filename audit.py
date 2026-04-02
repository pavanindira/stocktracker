"""
audit.py
Utility for writing AuditLog entries from any router.

Usage:
    from audit import log_action
    log_action(db, shop_id, request, action="SALE",
               entity_type="transaction", entity_id=txn.id,
               description=f"Sale of {len(items)} items totalling ${total}")
"""
import json
import logging
from sqlalchemy.orm import Session
from fastapi import Request
import models

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str, max_len: int = 200) -> str:
    """Sanitize value for audit log to prevent injection attacks."""
    if not value:
        return ""
    # Strip control characters and limit length
    sanitized = "".join(c for c in value if c.isprintable())
    return sanitized[:max_len]


def _actor(request: Request) -> tuple[str, str]:
    """Extract (actor_name, actor_role) from the session."""
    session = request.session
    name = (
        session.get("sub_user_name")
        or session.get("username")
        or session.get("user_name")
        or "unknown"
    )
    role = session.get("role") or "owner"
    return name, role


def log_action(
    db: Session,
    shop_id: int,
    request: Request,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """Write one audit log row. Fire-and-forget — does NOT commit."""
    actor_name, actor_role = _actor(request)
    entry = models.AuditLog(
        shop_id=shop_id,
        actor_name=actor_name,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        before_val=json.dumps(before) if before else None,
        after_val=json.dumps(after)  if after  else None,
    )
    db.add(entry)
    # Caller is responsible for db.commit()


def log_action_api(
    db: Session,
    shop_id: int,
    actor_name: str,
    actor_role: str,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """API (JWT) variant — actor supplied directly from token payload."""
    entry = models.AuditLog(
        shop_id=shop_id,
        actor_name=actor_name,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        before_val=json.dumps(before) if before else None,
        after_val=json.dumps(after)  if after  else None,
    )
    db.add(entry)
