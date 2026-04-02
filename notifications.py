"""
notifications.py
Background jobs for push notifications (Firebase FCM) and email digest.

Loaded in main.py via APScheduler — runs independently of HTTP requests.

Environment variables required:
  FCM_SERVER_KEY   — Firebase Cloud Messaging legacy server key
                     (or set to empty string to disable push notifications)
  SMTP_HOST        — e.g. smtp.gmail.com
  SMTP_PORT        — e.g. 587
  SMTP_USER        — sender email address
  SMTP_PASSWORD    — SMTP password or app password
  SMTP_FROM        — display name + address, e.g. "StockTracker <noreply@yourdomain.com>"
  DIGEST_HOUR      — 24h hour to send digest (default: 8 = 8am UTC)
"""
import os
import json
import ssl
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

import requests as http_requests
from sqlalchemy.orm import Session

from database import SessionLocal
import models
import fefo

logger = logging.getLogger("notifications")


# ─────────────────────────────────────────────────────────────────────────────
# FCM push notification
# ─────────────────────────────────────────────────────────────────────────────

FCM_URL       = "https://fcm.googleapis.com/fcm/send"
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")


def _send_fcm(token: str, title: str, body: str, data: dict | None = None) -> bool:
    """Send a single FCM notification to a device token. Returns True on success."""
    if not FCM_SERVER_KEY:
        return False
    payload = {
        "to": token,
        "notification": {"title": title, "body": body, "sound": "default"},
        "data": data or {},
        "priority": "high",
    }
    try:
        resp = http_requests.post(
            FCM_URL,
            headers={"Authorization": f"key={FCM_SERVER_KEY}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        result = resp.json()
        if result.get("failure", 0) > 0:
            logger.warning("FCM delivery failed for token %s: %s", token[:20], result)
            return False
        return True
    except Exception as e:
        logger.error("FCM request error: %s", e)
        return False


def _notify_shop(db: Session, shop: models.Shop, title: str, body: str,
                 data: dict | None = None) -> int:
    """Send FCM to all registered device tokens for a shop. Returns sent count."""
    tokens = db.query(models.DeviceToken).filter(
        models.DeviceToken.shop_id == shop.id
    ).all()
    sent = 0
    stale = []
    for dt in tokens:
        ok = _send_fcm(dt.token, title, body, data)
        if ok:
            sent += 1
        else:
            stale.append(dt.id)
    # Remove tokens that bounced
    if stale:
        db.query(models.DeviceToken).filter(
            models.DeviceToken.id.in_(stale)
        ).delete()
    
    # Clean up tokens inactive for more than 90 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    deleted = db.query(models.DeviceToken).filter(
        models.DeviceToken.shop_id == shop.id,
        models.DeviceToken.updated_at < cutoff
    ).delete()
    
    if deleted > 0:
        logger.info("Cleaned up %d stale device tokens for shop %d", deleted, shop.id)
    
    db.commit()
    return sent


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled jobs
# ─────────────────────────────────────────────────────────────────────────────

def check_low_stock_and_expiry():
    """
    Runs on a schedule. For every active shop:
      1. Send FCM push for low stock items
      2. Send FCM push for expiring/expired batches
    """
    db: Session = SessionLocal()
    try:
        shops = db.query(models.Shop).filter(
            models.Shop.is_active == True,
            models.Shop.is_admin  == False,
        ).all()

        for shop in shops:
            _push_low_stock(db, shop)
            _push_expiry(db, shop)
    except Exception as e:
        logger.error("check_low_stock_and_expiry error: %s", e)
    finally:
        db.close()


def _push_low_stock(db: Session, shop: models.Shop):
    low = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
        models.Product.stock_quantity <= models.Product.low_stock_threshold,
    ).order_by(models.Product.name).all()
    if not low:
        return
    names = ", ".join(p.name for p in low[:3])
    suffix = f" +{len(low)-3} more" if len(low) > 3 else ""
    _notify_shop(
        db, shop,
        title=f"⚠ Low Stock — {len(low)} product{'s' if len(low)!=1 else ''}",
        body=f"{names}{suffix}",
        data={"type": "low_stock", "count": str(len(low))},
    )


def _push_expiry(db: Session, shop: models.Shop):
    warnings = fefo.expiry_warnings(shop.id, db)
    expired  = len(warnings["expired"])
    soon     = len(warnings["expiring_soon"])
    if not expired and not soon:
        return
    parts = []
    if expired: parts.append(f"{expired} expired")
    if soon:    parts.append(f"{soon} expiring soon")
    _notify_shop(
        db, shop,
        title=f"⏰ Expiry Alert — {' · '.join(parts)}",
        body="Tap to view expiry report",
        data={"type": "expiry", "expired": str(expired), "expiring_soon": str(soon)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Daily email digest
# ─────────────────────────────────────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = max(1, min(65535, int(os.getenv("SMTP_PORT", "587"))))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", SMTP_USER)


def send_daily_digest():
    """
    Runs once a day. Sends each shop owner an HTML email summarising:
      - Low stock products
      - Expiring / expired batches
      - Yesterday's sales total
    """
    if not SMTP_HOST or not SMTP_USER:
        logger.info("SMTP not configured — skipping daily digest")
        return

    db: Session = SessionLocal()
    try:
        shops = db.query(models.Shop).filter(
            models.Shop.is_active == True,
            models.Shop.is_admin  == False,
            models.Shop.email.isnot(None),
        ).all()
        for shop in shops:
            try:
                _send_digest_email(db, shop)
            except Exception as e:
                logger.error("Digest email failed for shop %s: %s", shop.name, e)
    finally:
        db.close()


def _send_digest_email(db: Session, shop: models.Shop):
    from datetime import timedelta
    now       = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Low stock
    low = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
        models.Product.stock_quantity <= models.Product.low_stock_threshold,
    ).order_by(models.Product.stock_quantity).all()

    # Expiry
    warnings = fefo.expiry_warnings(shop.id, db)

    # Yesterday's sales
    from sqlalchemy import func as sqlfunc
    sales_total = db.query(sqlfunc.sum(models.Transaction.total_amount)).filter(
        models.Transaction.shop_id == shop.id,
        models.Transaction.transaction_type == models.TransactionType.SALE,
        models.Transaction.created_at >= yesterday.replace(hour=0, minute=0, second=0),
        models.Transaction.created_at < now.replace(hour=0, minute=0, second=0),
    ).scalar() or 0.0

    # Skip if nothing to report
    if not low and not warnings["expired"] and not warnings["expiring_soon"]:
        logger.debug("No issues for shop %s — skipping digest", shop.name)
        return

    html = _render_digest_html(shop, low, warnings, sales_total, yesterday)
    _send_email(
        to=shop.email,
        subject=f"📦 StockTracker Daily Digest — {shop.name} ({yesterday.strftime('%d %b %Y')})",
        html=html,
    )
    logger.info("Digest sent to %s (%s)", shop.email, shop.name)


def _render_digest_html(shop, low, warnings, sales_total, date) -> str:
    expired     = warnings["expired"]
    expiring    = warnings["expiring_soon"]
    low_rows    = "".join(
        f"<tr><td>{p.name}</td><td style='color:#e74c3c;font-weight:700;'>"
        f"{p.stock_quantity} {p.unit}</td>"
        f"<td style='color:#999;'>threshold: {p.low_stock_threshold}</td></tr>"
        for p in low[:20]
    )
    expiring_rows = ""
    for g in (expired + expiring):
        p = g["product"]
        for b in g["batches"][:3]:
            days = (b.expiry_date - date.date()).days if b.expiry_date else None
            status_txt = f"{abs(days)}d overdue" if days and days < 0 else f"{days}d left" if days else "—"
            color = "#e74c3c" if (days and days < 0) else "#f5a623"
            expiring_rows += (
                f"<tr><td>{p.name}</td>"
                f"<td style='font-family:monospace;'>{b.lot_number or '—'}</td>"
                f"<td style='font-family:monospace;'>{b.quantity}</td>"
                f"<td style='color:{color};font-weight:700;'>"
                f"{b.expiry_date.strftime('%d %b %Y') if b.expiry_date else '—'}</td>"
                f"<td style='color:{color};'>{status_txt}</td></tr>"
            )
    return f"""
<!DOCTYPE html><html><body style="font-family:sans-serif;color:#1a1a2e;background:#f5f5f5;padding:0;margin:0;">
<div style="max-width:640px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
  <div style="background:#7c6af7;padding:24px 32px;">
    <h1 style="color:#fff;margin:0;font-size:20px;">📦 StockTracker Daily Digest</h1>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;">{shop.name} · {date.strftime('%A, %d %B %Y')}</p>
  </div>
  <div style="padding:24px 32px;">
    <div style="display:flex;gap:16px;margin-bottom:24px;">
      <div style="flex:1;background:#f9f9f9;border-radius:8px;padding:16px;text-align:center;">
        <div style="font-size:11px;color:#999;letter-spacing:2px;text-transform:uppercase;">Yesterday's Sales</div>
        <div style="font-size:24px;font-weight:800;color:#7c6af7;margin-top:4px;">${sales_total:.2f}</div>
      </div>
      <div style="flex:1;background:#f9f9f9;border-radius:8px;padding:16px;text-align:center;">
        <div style="font-size:11px;color:#999;letter-spacing:2px;text-transform:uppercase;">Low Stock</div>
        <div style="font-size:24px;font-weight:800;color:#e74c3c;margin-top:4px;">{len(low)}</div>
      </div>
      <div style="flex:1;background:#f9f9f9;border-radius:8px;padding:16px;text-align:center;">
        <div style="font-size:11px;color:#999;letter-spacing:2px;text-transform:uppercase;">Expiry Alerts</div>
        <div style="font-size:24px;font-weight:800;color:#f5a623;margin-top:4px;">{len(expired)+len(expiring)}</div>
      </div>
    </div>
    {'<h2 style="font-size:15px;margin-bottom:8px;">⚠ Low Stock</h2><table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#f0f0f0;"><th style="text-align:left;padding:8px;">Product</th><th style="text-align:left;padding:8px;">Stock</th><th style="text-align:left;padding:8px;"> </th></tr></thead><tbody>' + low_rows + '</tbody></table>' if low else ''}
    {'<h2 style="font-size:15px;margin-top:24px;margin-bottom:8px;">⏰ Expiry Alerts</h2><table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#f0f0f0;"><th style="text-align:left;padding:8px;">Product</th><th style="text-align:left;padding:8px;">Lot</th><th style="text-align:left;padding:8px;">Qty</th><th style="text-align:left;padding:8px;">Expiry</th><th style="text-align:left;padding:8px;">Status</th></tr></thead><tbody>' + expiring_rows + '</tbody></table>' if expiring_rows else ''}
  </div>
  <div style="background:#f9f9f9;padding:16px 32px;font-size:11px;color:#999;">
    This is an automated digest from StockTracker. Log in to take action.
  </div>
</div>
</body></html>"""


def _send_email(to: str, subject: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))
    
    # Create SSL context with certificate verification
    context = ssl.create_default_context()
    
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()  # Re-identify after TLS
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to], msg.as_string())

