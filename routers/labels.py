"""
QR Label printing — web routes and shared PDF builder.
Each label is 50×30mm (Dymo / small shelf label).
Layout: QR code on left, text stack on right.
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models, auth
import io, qrcode
from fpdf import FPDF

router = APIRouter(prefix="/products/labels")
templates = Jinja2Templates(directory="templates")

# Label dimensions (mm)
LW, LH = 50, 30


def get_shop(request: Request, db: Session):
    shop_id = request.session.get("shop_id")
    if not shop_id:
        return None
    return db.query(models.Shop).filter(models.Shop.id == shop_id).first()


# ── Web: selection page ───────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def labels_select(
    request: Request,
    db: Session = Depends(get_db),
    search: str = "",
    category_id: str = "",
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    query = db.query(models.Product).filter(
        models.Product.shop_id == shop.id,
        models.Product.is_active == True,
    )
    if search:
        # Escape LIKE wildcards
        esc = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(models.Product.name.ilike(f"%{esc}%", escape='\\'))
    if category_id and category_id.isdigit():
        query = query.filter(models.Product.category_id == int(category_id))
    products = query.order_by(models.Product.name).all()
    categories = db.query(models.Category).filter(
        models.Category.shop_id == shop.id
    ).order_by(models.Category.name).all()

    return templates.TemplateResponse("products/labels.html", {
        "request": request, "shop": shop,
        "products": products, "categories": categories,
        "search": search, "selected_category": category_id,
    })


# ── Web: generate PDF ─────────────────────────────────────────────────────────

@router.post("/print")
async def labels_print(
    request: Request,
    db: Session = Depends(get_db),
):
    shop = get_shop(request, db)
    if not shop:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    ids  = [int(v) for k, v in form.multi_items() if k == "product_ids"]
    if not ids:
        return RedirectResponse(url="/products/labels?error=no_selection",
                                status_code=302)

    products = db.query(models.Product).filter(
        models.Product.id.in_(ids),
        models.Product.shop_id == shop.id,
    ).order_by(models.Product.name).all()

    pdf_bytes = build_labels_pdf(products, shop.name)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="labels.pdf"'},
    )


# ── PDF builder (shared with API) ─────────────────────────────────────────────

def build_labels_pdf(products: list, shop_name: str) -> bytes:
    """
    Generate a multi-page PDF where each page = one 50×30mm label.
    Layout:
      Left  (0–20mm)  : QR code
      Right (21–49mm) : shop name / product name / category / price / SKU
    """
    pdf = FPDF(unit="mm", format=(LW, LH))
    pdf.set_margins(0, 0, 0)
    pdf.set_auto_page_break(False)

    for p in products:
        pdf.add_page()
        _draw_label(pdf, p, shop_name)

    return bytes(pdf.output())


def _draw_label(pdf: FPDF, p: models.Product, shop_name: str):
    # ── Background ────────────────────────────────────────────────────────────
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, LW, LH, "F")

    # ── QR code ───────────────────────────────────────────────────────────────
    qr_content = p.sku if p.sku else f"PRODUCT:{p.id}"
    qr = qrcode.QRCode(version=1, box_size=4, border=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_content)
    qr.make(fit=True)
    qr_img  = qr.make_image(fill_color="black", back_color="white")
    qr_buf  = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    # QR occupies a 22×22mm square, centred vertically in the 30mm label
    qr_size = 22
    qr_y    = (LH - qr_size) / 2
    pdf.image(qr_buf, x=1, y=qr_y, w=qr_size, h=qr_size)

    # Thin separator line
    pdf.set_draw_color(220, 220, 230)
    pdf.set_line_width(0.2)
    pdf.line(24, 2, 24, LH - 2)

    # ── Right-side text block ─────────────────────────────────────────────────
    x, w = 25.5, LW - 26.5   # left edge and width of text column
    y    = 3.5

    # Shop name
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", "", 5.5)
    pdf.set_text_color(150, 150, 165)
    shop_display = shop_name.upper()
    if len(shop_display) > 20:
        shop_display = shop_display[:19] + "…"
    pdf.cell(w, 3.5, shop_display, ln=True)
    y += 3.5

    # Product name (bold, wraps to 2 lines)
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(15, 17, 23)
    name = p.name
    if len(name) > 28:
        name = name[:27] + "…"
    # Manually wrap at ~16 chars per line given the column width
    if len(name) <= 16:
        pdf.cell(w, 4, name, ln=True)
        y += 4
    else:
        # split on last space before char 17
        split = name.rfind(" ", 0, 17)
        if split == -1:
            split = 16
        line1 = name[:split]
        line2 = name[split:].strip()
        pdf.cell(w, 3.5, line1, ln=True)
        pdf.set_xy(x, y + 3.5)
        pdf.cell(w, 3.5, line2, ln=True)
        y += 7

    # Category badge
    if p.category_obj:
        pdf.set_xy(x, y + 0.5)
        cat_name = p.category_obj.name
        if len(cat_name) > 14:
            cat_name = cat_name[:13] + "…"
        # Draw coloured background pill
        try:
            hex_c = p.category_obj.color.lstrip("#")
            r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
        except Exception:
            r, g, b = 124, 106, 247
        # Light background
        pdf.set_fill_color(int(r * 0.2 + 220), int(g * 0.2 + 220), int(b * 0.2 + 220))
        pdf.set_draw_color(r, g, b)
        pdf.set_line_width(0.15)
        badge_w = min(len(cat_name) * 1.5 + 2, w)
        pdf.rect(x, y + 0.5, badge_w, 3.2, "FD")
        pdf.set_xy(x + 0.5, y + 0.8)
        pdf.set_font("Helvetica", "B", 5)
        pdf.set_text_color(r, g, b)
        pdf.cell(badge_w - 1, 2.5, cat_name.upper(), ln=True)
        y += 4.5

    # Price
    pdf.set_xy(x, y + 0.5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(15, 17, 23)
    price_str = f"${p.selling_price:.2f}"
    pdf.cell(w, 5, price_str, ln=True)
    y += 5.5

    # SKU / barcode text
    if p.sku:
        pdf.set_xy(x, y)
        pdf.set_font("Courier", "", 5.5)
        pdf.set_text_color(150, 150, 165)
        sku = p.sku if len(p.sku) <= 20 else p.sku[:19] + "…"
        pdf.cell(w, 3, sku, ln=True)

    # Bottom accent strip
    cat_color = p.category_obj.color if p.category_obj else "#f5a623"
    try:
        hex_c = cat_color.lstrip("#")
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    except Exception:
        r, g, b = 245, 166, 35
    pdf.set_fill_color(r, g, b)
    pdf.rect(0, LH - 1.5, LW, 1.5, "F")
