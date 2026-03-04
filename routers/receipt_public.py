"""
Public (no-auth) receipt pages.
  POST /transactions/{id}/share    — generate/return a share token
  GET  /receipt/{token}            — public read-only HTML receipt
  GET  /receipt/{token}/pdf        — public PDF download
"""
import secrets
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, io

router    = APIRouter()
templates = Jinja2Templates(directory="templates")

TOKEN_BYTES = 24   # 48 hex chars — plenty of entropy


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


# ── Generate / retrieve share token (called by the transactions detail page) ──

@router.post("/transactions/{transaction_id}/share", response_class=JSONResponse)
async def generate_share_link(
    request: Request,
    transaction_id: int,
    db: Session = Depends(get_db),
):
    shop = get_shop(request, db)
    if not shop:
        raise HTTPException(status_code=401, detail="Not authenticated")

    txn = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.shop_id == shop.id,
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if not txn.share_token:
        txn.share_token = secrets.token_hex(TOKEN_BYTES)
        db.commit()

    base_url = str(request.base_url).rstrip("/")
    return {"url": f"{base_url}/receipt/{txn.share_token}"}


# ── Public receipt HTML ───────────────────────────────────────────────────────

@router.get("/receipt/{token}", response_class=HTMLResponse)
async def public_receipt(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    txn = db.query(models.Transaction).filter(
        models.Transaction.share_token == token
    ).first()
    if not txn:
        return HTMLResponse(_not_found_html(), status_code=404)

    shop = db.query(models.Shop).filter(models.Shop.id == txn.shop_id).first()
    subtotal = txn.total_amount - txn.tax_amount

    return templates.TemplateResponse("receipt_public.html", {
        "request": request,
        "txn": txn,
        "shop": shop,
        "subtotal": subtotal,
        "token": token,
    })


# ── Public receipt PDF ────────────────────────────────────────────────────────

@router.get("/receipt/{token}/pdf")
async def public_receipt_pdf(token: str, db: Session = Depends(get_db)):
    txn = db.query(models.Transaction).filter(
        models.Transaction.share_token == token
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Receipt not found")

    shop = db.query(models.Shop).filter(models.Shop.id == txn.shop_id).first()

    from routers.api import _build_receipt_pdf
    pdf_bytes = _build_receipt_pdf(txn, shop)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="receipt_{txn.id}.pdf"'},
    )


def _not_found_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Receipt Not Found</title>
<style>
  body{background:#0f1117;color:#e8eaf0;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
  .box{text-align:center;padding:40px;}
  h1{font-size:48px;color:#f5a623;margin:0 0 8px;}
  p{color:#7880a0;}
</style>
</head>
<body><div class="box">
  <h1>404</h1>
  <h2>Receipt Not Found</h2>
  <p>This link may have expired or the receipt does not exist.</p>
</div></body>
</html>"""
