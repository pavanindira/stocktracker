# StockTracker

A multi-shop inventory management system — **web app** (FastAPI + Jinja2) and **mobile app** (Flutter), backed by PostgreSQL with full offline support.

---

## Feature Overview

### Web App
| Area | Features |
|------|----------|
| **Dashboard** | Live stats · low-stock widget · expiry alerts · monthly sales summary |
| **Products** | Full CRUD · SKU · category · pricing · units · low-stock threshold · default expiry · preferred supplier · reorder qty |
| **Barcode scan** | Browser camera scanner · Open Food Facts auto-fill |
| **CSV Import** | Drag-and-drop upload · row-by-row validation preview · skip or update duplicates · auto-create categories |
| **QR Label printing** | 50×30mm Dymo-style labels · QR code + name + price + SKU + category · PDF download |
| **Categories** | Colour-coded product categories |
| **Transactions** | Sales · purchases · adjustments · multi-item cart · tax rate · reference number |
| **FEFO** | Per-batch expiry tracking · oldest-expiry deducted first on sale · lot numbers on receipts |
| **Receipts** | PDF receipts · shareable public receipt link (no login required) |
| **Reports** | Date-range analytics · top sellers · stock status · expiry report · CSV exports |
| **Suppliers** | Supplier CRUD · link to products · purchase history · reorder suggestions grouped by supplier · email order shortcut |
| **Stocktake** | Physical count sessions · AJAX count entry · variance review · auto-creates adjustment transactions on commit |
| **Team management** | Cashier / Manager sub-accounts per shop · role-based access controls |
| **Admin panel** | System-level shop management at `/admin` |

### Mobile App (Flutter — iOS & Android)
| Screen | Features |
|--------|----------|
| **Login** | Server URL + credentials · role-aware session |
| **Dashboard** | Stats cards · low-stock list · expiry alerts |
| **Products** | Searchable list · category filter · low-stock toggle |
| **Scan** | Sale / Restock / Add Product modes · barcode scanner |
| **Cart** | Multi-item sale · quantity controls · tax rate · expiry warning dialog before confirm |
| **Receipt** | Transaction summary · PDF download |
| **Transactions** | Paginated history · filter by type |
| **Categories** | Create / delete with colour picker |
| **Labels** | Product checklist · download 50×30mm PDF labels |
| **Import** | Pick CSV · preview rows · confirm import |
| **Suppliers** | Supplier list · Reorder tab with deficit view |
| **Stocktake** | Create count · per-item entry with live variance · commit |
| **Team** | View / add / remove sub-accounts (owner only) |
| **Offline mode** | Full SQLite cache · sale and restock queue · auto-sync on reconnect |

---

## Role Permissions

| Feature | Cashier | Manager | Owner |
|---------|:-------:|:-------:|:-----:|
| Record sales | ✅ | ✅ | ✅ |
| Record purchases / adjustments | ❌ | ✅ | ✅ |
| Add / edit products | ❌ | ✅ | ✅ |
| Manage categories | ❌ | ✅ | ✅ |
| View reports / expiry report | ❌ | ✅ | ✅ |
| See cost prices | ❌ | ✅ | ✅ |
| Manage suppliers / run stocktake | ❌ | ✅ | ✅ |
| Manage team members | ❌ | ❌ | ✅ |

> System Admin accounts can only access `/admin` and cannot log in to the mobile app.

---

## Project Structure

```
stocktracker/
│
├── main.py                            # FastAPI application entry point, router registration
├── database.py                        # SQLAlchemy engine & session factory
├── models.py                          # All ORM models (see Database Schema below)
├── auth.py                            # Password hashing, session helpers, role guards
├── fefo.py                            # First-Expiry First-Out stock engine
├── seed.py                            # Seeds default admin account on first startup
│
├── routers/
│   ├── __init__.py
│   ├── auth_router.py                 # Web login / logout
│   ├── admin.py                       # /admin — system-level shop management
│   ├── dashboard.py                   # Shop dashboard (web)
│   ├── categories.py                  # Category CRUD (web)
│   ├── products.py                    # Product CRUD + barcode lookup (web)
│   ├── transactions.py                # Transaction create / list / detail (web)
│   ├── reports.py                     # Reports + expiry report + CSV exports
│   ├── team.py                        # Team / sub-user management (owner only)
│   ├── labels.py                      # QR label PDF generation (web + shared builder)
│   ├── import_csv.py                  # Bulk CSV product import (web)
│   ├── receipt_public.py              # Public receipt pages — no auth required
│   ├── suppliers.py                   # Supplier CRUD + reorder suggestions
│   ├── stocktake.py                   # Stocktake flow: create → count → review → commit
│   └── api.py                         # Mobile REST API — all /api/* JWT-protected endpoints
│
├── templates/                         # Jinja2 HTML templates
│   ├── base.html                      # Master layout with role-aware sidebar nav
│   ├── login.html
│   ├── dashboard.html
│   ├── receipt_public.html            # Standalone public receipt (no base.html)
│   ├── admin/
│   │   ├── base_admin.html
│   │   ├── index.html
│   │   ├── shop_form.html
│   │   ├── reset_password.html
│   │   └── change_password.html
│   ├── categories/
│   │   ├── index.html
│   │   └── form.html
│   ├── products/
│   │   ├── index.html                 # Product list with expiry column + badges
│   │   ├── form.html                  # Create/edit: supplier, expiry, reorder qty
│   │   ├── scan.html                  # Browser barcode scanner
│   │   ├── labels.html                # Label selection + live preview
│   │   ├── import.html                # CSV upload + validation preview table
│   │   └── import_done.html           # Import completion summary
│   ├── transactions/
│   │   ├── index.html
│   │   ├── form.html
│   │   └── detail.html                # Includes Share Receipt button + JS
│   ├── reports/
│   │   ├── index.html
│   │   └── expiry.html                # FEFO expiry report with days-left pills
│   ├── team/
│   │   ├── index.html
│   │   └── form.html
│   ├── suppliers/
│   │   ├── index.html                 # Supplier list with reorder alert badges
│   │   ├── form.html                  # Create / edit supplier
│   │   ├── detail.html                # Profile + linked products + purchase history
│   │   └── reorder.html               # Reorder suggestions grouped by supplier
│   └── stocktake/
│       ├── index.html                 # Stocktake list with progress bars
│       ├── new.html                   # Create form with optional category filter
│       ├── count.html                 # AJAX count entry with sticky progress bar
│       ├── review.html                # Variance summary + commit button
│       └── done.html                  # Completion confirmation with adjustment log
│
├── static/
│   └── js/
│       └── html5-qrcode.min.js        # Barcode scanner library (download separately)
│
├── mobile/                            # Flutter mobile app
│   ├── pubspec.yaml
│   ├── android/app/src/main/
│   │   └── AndroidManifest.xml        # Camera + storage permissions
│   ├── ios/Runner/
│   │   └── Info.plist                 # Camera + file access usage strings
│   └── lib/
│       ├── main.dart
│       ├── theme.dart                 # Shared colours, input decorations, constants
│       ├── services/
│       │   ├── api_service.dart       # All HTTP calls to the backend
│       │   ├── auth_service.dart      # Token, role, and server URL persistence
│       │   ├── local_db.dart          # SQLite cache for offline support
│       │   └── sync_service.dart      # Delta sync + offline transaction queue flush
│       └── screens/
│           ├── login_screen.dart
│           ├── main_shell.dart        # Bottom nav · role-based tabs · offline chip
│           ├── dashboard_screen.dart
│           ├── products_screen.dart
│           ├── scan_screen.dart       # Barcode scanner (sale / restock / add modes)
│           ├── cart_screen.dart       # Multi-item cart with expiry warning dialog
│           ├── receipt_screen.dart    # Post-sale receipt + PDF download
│           ├── transactions_screen.dart
│           ├── transaction_sheet.dart
│           ├── categories_screen.dart
│           ├── add_product_sheet.dart
│           ├── labels_screen.dart     # QR label PDF download
│           ├── import_screen.dart     # CSV bulk import: pick → preview → confirm
│           ├── team_screen.dart       # Sub-user management (owner only)
│           ├── suppliers_screen.dart  # Supplier list + Reorder tab
│           └── stocktake_screen.dart  # Stocktake list + count entry + commit
│
├── migrate_categories.sql             # Adds categories table
├── migrate_roles.sql                  # Adds shop_sub_users, tax columns
├── migrate_import_and_share.sql       # Adds share_token on transactions
├── migrate_fefo.sql                   # Adds product_batches, expiry date columns
├── migrate_suppliers_stocktake.sql    # Adds suppliers, stocktakes, stocktake_items
│
├── requirements.txt
└── .env.example
```

---

## Database Schema

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `shops` | Shop accounts (one per store) | `is_admin`, `is_active` |
| `shop_sub_users` | Cashier / Manager accounts | `shop_id`, `role` enum (`owner` / `manager` / `cashier`) |
| `categories` | Product categories | `shop_id`, `color` (hex) |
| `products` | Inventory items | `shop_id`, `supplier_id`, `default_expiry_date`, `reorder_quantity` |
| `product_batches` | Per-restock lots for FEFO | `product_id`, `expiry_date`, `quantity`, `lot_number` |
| `transactions` | Sales / purchases / adjustments | `shop_id`, `transaction_type`, `supplier_id`, `share_token`, `tax_rate` |
| `transaction_items` | Line items per transaction | `transaction_id`, `product_id`, `batch_id`, `lot_number` (snapshot) |
| `suppliers` | Supplier directory | `shop_id`, `lead_time_days`, `contact_name`, `email` |
| `stocktakes` | Physical count sessions | `shop_id`, `status` (`draft` → `in_progress` → `completed`) |
| `stocktake_items` | Per-product count rows | `stocktake_id`, `system_quantity` (snapshot), `counted_quantity` |

---

## Backend Setup

### 1. Prerequisites
- Python 3.10+
- PostgreSQL 13+

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/stocktracker
SECRET_KEY=replace-with-a-long-random-string

# Used on first startup only — change immediately after
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@1234
ADMIN_NAME=System Administrator
```

### 4. Download barcode library (web scanner)

```bash
curl -L "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js" \
     -o static/js/html5-qrcode.min.js
```

### 5. Create the database and run all migrations

```bash
# Create database
psql -U postgres -c "CREATE DATABASE stocktracker;"

# Run migrations in order (safe to re-run — all use IF NOT EXISTS)
psql -U postgres -d stocktracker -f migrate_categories.sql
psql -U postgres -d stocktracker -f migrate_roles.sql
psql -U postgres -d stocktracker -f migrate_import_and_share.sql
psql -U postgres -d stocktracker -f migrate_fefo.sql
psql -U postgres -d stocktracker -f migrate_suppliers_stocktake.sql

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Tables are created automatically by SQLAlchemy on startup. On first run, the seed script prints:

```
[seed] Default admin created — username: 'admin' | password: 'Admin@1234'
[seed] ⚠  Change the admin password immediately via the Admin panel!
```

---

## Mobile App Setup

### Prerequisites
- Flutter SDK 3.x — [flutter.dev/docs/get-started/install](https://flutter.dev/docs/get-started/install)
- Android Studio or Xcode

### Install and run

```bash
cd mobile
flutter pub get
flutter run               # connected device or emulator
flutter build apk         # Android release APK
flutter build ipa         # iOS (requires Xcode on macOS)
```

### Connecting to the backend

Enter the **Server URL** on the login screen:

| Environment | Example URL |
|-------------|-------------|
| Same Wi-Fi network | `http://192.168.1.100:8000` |
| LAN with hostname | `http://stocktracker.local:8000` |
| Public server | `https://yourdomain.com` |

> Use HTTPS in production — browsers and Android 9+ block camera access on plain HTTP.

---

## REST API Reference

All endpoints are prefixed with `/api`. Authentication uses **Bearer JWT** tokens issued at login.

### Authentication

#### `POST /api/auth/login`

**Request** (`application/x-www-form-urlencoded`):
```
username=myshop&password=secret
```

**Response:**
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "shop_id": 3,
  "shop_name": "Green Valley Store",
  "role": "owner",
  "user_name": "owner"
}
```

Tokens are valid for **7 days**. Include in all subsequent requests:
```
Authorization: Bearer <access_token>
```

---

### Dashboard · `GET /api/dashboard`

```json
{
  "total_products": 42,
  "low_stock_count": 3,
  "low_stock_items": [...],
  "monthly_sales": 1840.50,
  "total_stock_value": 12300.00,
  "expired_count": 1,
  "expiring_count": 4,
  "expiring_soon": [
    { "id": 7, "name": "Yoghurt 500g", "expiry_date": "2026-03-10", "status": "soon" }
  ]
}
```

---

### Products

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/products` | List — supports `search`, `category_id`, `low_stock_only`, `updated_since` |
| `GET` | `/api/products/barcode/{barcode}` | Lookup by barcode (inventory first, then Open Food Facts) |
| `POST` | `/api/products` | Create a product |
| `GET` | `/api/products/{id}/batches` | List FEFO batches for a product |

Product objects include `expiry_status` (`ok` / `soon` / `expired` / `none`) and `earliest_expiry`.

---

### Transactions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/transactions` | Paginated list — `type`, `limit`, `offset` params |
| `GET` | `/api/transactions/{id}` | Single transaction with line items and lot numbers |
| `POST` | `/api/transactions` | Create sale / purchase / adjustment |
| `POST` | `/api/transactions/{id}/share` | Generate / retrieve shareable public receipt URL |
| `GET` | `/api/transactions/{id}/receipt` | Download PDF receipt |

**Create transaction request body:**
```json
{
  "transaction_type": "sale",
  "reference": "POS-1042",
  "tax_rate": 10.0,
  "items": [
    {
      "product_id": 5,
      "quantity": 2,
      "unit_price": 1.20,
      "expiry_date": "2026-06-01",
      "lot_number": "LOT-A1"
    }
  ]
}
```

Stock rules: **sale** → FEFO deduction (oldest expiry first). **purchase** → creates a new batch. **adjustment** → sets absolute stock quantity.

---

### Labels · `GET /api/labels?ids=1,2,3`

Returns a multi-page PDF — one 50×30mm label per product ID.

---

### CSV Import · `POST /api/products/import`

Query params: `on_duplicate=skip|update` · `commit=false|true`

Body: multipart file upload or `{"csv": "...raw CSV text..."}`.

With `commit=false` (default) returns a preview list with per-row status. With `commit=true` writes to the database and returns `{created, updated, skipped}`.

---

### Suppliers

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/suppliers` | List all active suppliers |
| `GET` | `/api/suppliers/reorder` | Products at or below threshold, with supplier and deficit info |

---

### Stocktake

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stocktakes` | List stocktake sessions (most recent 20) |
| `POST` | `/api/stocktakes` | Create new stocktake and snapshot all product quantities |
| `GET` | `/api/stocktakes/{id}/items` | Fetch all line items with system and counted quantities |
| `PATCH` | `/api/stocktakes/{id}/items/{item_id}` | Save a counted quantity for one item |
| `POST` | `/api/stocktakes/{id}/commit` | Apply variances, create adjustment transactions, mark complete |

---

### Expiry · `GET /api/expiry`

Returns all expired and expiring-soon batches for the authenticated shop.

---

### Sync · `GET /api/sync?updated_since=<ISO datetime>`

Returns all products and categories updated after the given timestamp. Used by the mobile app for efficient delta cache refreshes.

---

## Public Receipt Links

Any transaction can be shared as a permanent, no-login-required page:

1. Click **🔗 Share Receipt** on the transaction detail page (web), or call `POST /api/transactions/{id}/share` (mobile / API).
2. A unique 48-character random token is generated and stored on the transaction.
3. The public URL is: `https://yourdomain.com/receipt/{token}`
4. Anyone with the link can view the HTML receipt and download the PDF at `…/receipt/{token}/pdf`.

Lot numbers are shown per line item where available.

---

## FEFO — First-Expiry First-Out

Every **purchase** transaction creates a `ProductBatch` row recording quantity, expiry date, and optional lot number. Every **sale** calls `fefo.deduct_fefo()` in `fefo.py`, which drains batches in ascending expiry date order. The `batch_id` and `lot_number` are snapshotted onto each `TransactionItem` for full receipt traceability.

Expiry warnings surface in:
- **Dashboard** — Expiry Alerts stat card and widget table (expired + expiring within 30 days)
- **Products list** — colour-coded Expiry column (green / amber / red)
- **Reports → Expiry Report** — full list sorted by urgency, with days-overdue and days-left pills
- **Mobile cart** — warning dialog before completing a sale if any item has expired or expiring-soon stock

---

## Offline Mode (Mobile)

| Action | Online | Offline |
|--------|--------|---------|
| View dashboard / products / transactions | Live API | SQLite cache |
| Record a sale | Sent immediately | Queued in SQLite, stock updated optimistically |
| Record a restock | Sent immediately | Queued in SQLite |
| Add new product / category | Sent immediately | ❌ Not supported offline |

When the app reconnects, `sync_service.dart` flushes the queue in submission order, then runs a delta sync to pull down any remote changes. The app bar shows a badge with the count of pending transactions.

---

## Security

| Concern | Approach |
|---------|----------|
| Web passwords | Argon2id via `passlib[argon2]` |
| Web sessions | Signed server-side cookies via `itsdangerous` |
| Mobile auth | 7-day JWT via `python-jose`; admin accounts explicitly blocked from mobile login |
| Role enforcement | Every route checks the session role; cashiers cannot reach manager / owner routes |
| Shop isolation | All DB queries filter by `shop_id` from the session or JWT claim |
| Public receipts | Share tokens are 48 random hex characters; no cost prices are exposed |
| Self-registration | Disabled — the system admin creates all shop accounts |

---

## Production Deployment

```bash
# Backend — 4 Uvicorn workers behind Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Mobile release builds
cd mobile
flutter build apk --release    # Android APK
flutter build ipa               # iOS (macOS + Xcode required)
```

**Pre-launch checklist:**
- [ ] Put Nginx in front with a valid TLS certificate (required for camera access and secure cookies)
- [ ] Set a strong random `SECRET_KEY` in `.env`
- [ ] Change the default admin password immediately after first startup
- [ ] Confirm `static/js/html5-qrcode.min.js` is present
- [ ] Restrict direct PostgreSQL port access to the app server only
