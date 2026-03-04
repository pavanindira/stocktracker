# StockTracker

A multi-shop stock inventory management system — **web app** (FastAPI + Jinja2) and **mobile app** (Flutter), sharing a single PostgreSQL backend.

---

## Features

### Web App
- **System admin** — manages all shops, creates accounts, resets passwords, activates/deactivates shops
- **Multi-shop isolation** — each shop sees only its own data
- **Categories** — colour-coded product categories with custom labels
- **Products** — full CRUD with SKU, category, pricing, units, and low-stock thresholds
- **Barcode scan** — browser-based camera scanner with Open Food Facts auto-fill
- **Transactions** — sales, purchases, and manual adjustments with multi-item support
- **Dashboard** — live stats, low-stock alerts, monthly sales summary
- **Reports** — date-range analytics, top sellers, stock status, CSV exports

### Mobile App (Flutter — iOS & Android)
- **Login** — connects to your self-hosted FastAPI backend over the local network or internet
- **Dashboard** — stats cards and low-stock alert list
- **Products** — searchable list with category filter and low-stock toggle
- **Barcode scan** — three modes: *Add Product*, *Sale*, *Restock*
- **Transaction history** — paginated list filterable by sale / purchase / adjustment
- **Category management** — create and delete categories with colour picker
- **Offline mode** — full SQLite cache; sales and restocks queue locally and auto-sync when back online

---

## Roles

| Role | Access |
|------|--------|
| **System Admin** | `/admin` web panel — manages shops, cannot use the mobile app |
| **Shop User** | Web app at `/` and mobile app — manages their own inventory |

> Self-registration is disabled. All shop accounts are created by the administrator.

---

## Project Structure

```
stocktracker/
├── main.py                      # FastAPI entry point
├── seed.py                      # Creates default admin on first startup
├── database.py                  # SQLAlchemy engine & session
├── models.py                    # ORM: Shop, Category, Product, Transaction, TransactionItem
├── auth.py                      # Argon2 hashing, session helpers, JWT helpers
├── routers/
│   ├── auth_router.py           # Web login / logout
│   ├── admin.py                 # Admin panel
│   ├── dashboard.py             # Shop dashboard
│   ├── categories.py            # Category CRUD (web)
│   ├── products.py              # Product CRUD + barcode lookup (web)
│   ├── transactions.py          # Transactions (web)
│   ├── reports.py               # Reports + CSV export (web)
│   └── api.py                   # Mobile REST API (JWT, all /api/* routes)
├── templates/                   # Jinja2 templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── admin/
│   ├── categories/
│   ├── products/
│   │   ├── index.html
│   │   ├── form.html
│   │   └── scan.html
│   ├── transactions/
│   └── reports/
├── static/
│   └── js/
│       └── html5-qrcode.min.js  # Local barcode library (download separately)
├── mobile/                      # Flutter app
│   ├── pubspec.yaml
│   ├── lib/
│   │   ├── main.dart
│   │   ├── theme.dart           # Shared colours and input styles
│   │   ├── services/
│   │   │   ├── auth_service.dart    # Token + server URL persistence
│   │   │   ├── api_service.dart     # All HTTP calls to the backend
│   │   │   ├── local_db.dart        # SQLite cache (offline support)
│   │   │   └── sync_service.dart    # Delta sync + offline queue flush
│   │   └── screens/
│   │       ├── login_screen.dart
│   │       ├── main_shell.dart      # Bottom nav + online/offline status
│   │       ├── dashboard_screen.dart
│   │       ├── products_screen.dart
│   │       ├── scan_screen.dart
│   │       ├── transactions_screen.dart
│   │       ├── categories_screen.dart
│   │       ├── add_product_sheet.dart
│   │       └── transaction_sheet.dart
│   ├── android/app/src/main/
│   │   └── AndroidManifest.xml
│   └── ios/Runner/
│       └── Info.plist
├── migrate_categories.sql       # One-time DB migration for categories
├── requirements.txt
└── .env.example
```

---

## Backend Setup

### 1. Prerequisites
- Python 3.10+
- PostgreSQL

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate     # Linux/macOS
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 3. Download barcode scanning library (web)

```bash
curl -L "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js" \
     -o static/js/html5-qrcode.min.js
```

### 4. Configure environment

```bash
cp .env.example .env
```

```env
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/stocktracker
SECRET_KEY=replace-with-a-long-random-string

# Admin credentials (used on first startup only)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@1234
ADMIN_NAME=System Administrator
```

### 5. Create database and run

```bash
psql -U postgres -c "CREATE DATABASE stocktracker;"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Tables are created automatically. The default admin is seeded on first run:

```
[seed] Default admin created — username: 'admin' | password: 'Admin@1234'
[seed] ⚠  Change the admin password immediately via the Admin panel!
```

---

## Mobile App Setup

### Prerequisites
- Flutter SDK 3.x — [flutter.dev/docs/get-started/install](https://flutter.dev/docs/get-started/install)
- Android Studio or Xcode (for device/emulator)

### Install and run

```bash
cd mobile
flutter pub get
flutter run              # connected device or emulator
flutter build apk        # Android release APK
flutter build ipa        # iOS (requires Xcode on macOS)
```

### Connecting to the backend

On the login screen, enter the **Server URL** pointing to your running FastAPI instance:

| Setup | URL example |
|-------|-------------|
| Same Wi-Fi network | `http://192.168.1.100:8000` |
| LAN with hostname | `http://stocktracker.local:8000` |
| Public server | `https://yourdomain.com` |

> **Note:** Browsers and Android 9+ block plain HTTP on real devices in some scenarios. Use HTTPS in production (see deployment notes).

Find your local IP with `ipconfig` (Windows) or `ifconfig` / `ip a` (Linux/macOS).

---

## REST API Reference

All endpoints are prefixed with `/api`. Authentication uses **Bearer JWT tokens** issued at login.

### Authentication

#### `POST /api/auth/login`
Authenticate a shop user and receive a JWT token.

**Request** (`application/x-www-form-urlencoded`):
```
username=myshop&password=mypassword
```

**Response:**
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "shop_id": 3,
  "shop_name": "Green Valley Store"
}
```

Tokens are valid for **7 days**. All subsequent requests must include:
```
Authorization: Bearer <access_token>
```

---

### Dashboard

#### `GET /api/dashboard`
Returns summary stats for the authenticated shop.

```json
{
  "total_products": 42,
  "low_stock_count": 3,
  "low_stock_items": [
    {"id": 5, "name": "Rice 1kg", "stock": 2, "threshold": 10, "unit": "pcs"}
  ],
  "monthly_sales": 1840.50,
  "total_stock_value": 12300.00
}
```

---

### Sync

#### `GET /api/sync?updated_since=<ISO datetime>`
Returns all products and categories, optionally filtered to only items updated after `updated_since`. Used by the mobile app to refresh its local SQLite cache efficiently.

```json
{
  "synced_at": "2025-08-01T10:30:00",
  "products": [ ... ],
  "categories": [ ... ]
}
```

---

### Categories

#### `GET /api/categories`
List all categories for the shop.

#### `POST /api/categories`
Create a new category.
```json
{ "name": "Beverages", "description": "Drinks and liquids", "color": "#3498db" }
```

#### `DELETE /api/categories/{id}`
Delete a category. Products in the category are unlinked (not deleted).

---

### Products

#### `GET /api/products`
List products with optional filters.

| Query param | Type | Description |
|-------------|------|-------------|
| `search` | string | Filter by name (case-insensitive) |
| `category_id` | int | Filter by category |
| `low_stock_only` | bool | Only return low-stock items |
| `updated_since` | ISO datetime | Delta sync — only items updated after this time |

#### `GET /api/products/barcode/{barcode}`
Look up a barcode. Checks the shop's inventory first, then falls back to Open Food Facts.

```json
{
  "found_in_inventory": false,
  "barcode": "5449000000996",
  "off_data": {
    "name": "Coca-Cola 500ml",
    "brand": "Coca-Cola",
    "description": "500 ml",
    "image_url": "https://..."
  }
}
```

#### `POST /api/products`
Create a new product.
```json
{
  "name": "Coca-Cola 500ml",
  "sku": "5449000000996",
  "category_id": 2,
  "unit": "pcs",
  "cost_price": 0.60,
  "selling_price": 1.20,
  "stock_quantity": 48,
  "low_stock_threshold": 12
}
```

---

### Transactions

#### `GET /api/transactions`
Paginated transaction history.

| Query param | Type | Description |
|-------------|------|-------------|
| `type` | `sale` \| `purchase` \| `adjustment` | Filter by type |
| `limit` | int | Page size (default 50) |
| `offset` | int | Pagination offset |

**Response:**
```json
{
  "total": 120,
  "offset": 0,
  "limit": 50,
  "items": [
    {
      "id": 88,
      "transaction_type": "sale",
      "reference": "INV-001",
      "total_amount": 14.40,
      "items_count": 3,
      "created_at": "2025-07-30T09:15:00"
    }
  ]
}
```

#### `GET /api/transactions/{id}`
Get a single transaction with full line items.

```json
{
  "id": 88,
  "transaction_type": "sale",
  "total_amount": 14.40,
  "items": [
    {
      "product_id": 5,
      "product_name": "Coca-Cola 500ml",
      "quantity": 3,
      "unit_price": 1.20,
      "subtotal": 3.60,
      "unit": "pcs"
    }
  ]
}
```

#### `POST /api/transactions`
Record a sale, purchase, or adjustment.
```json
{
  "transaction_type": "sale",
  "reference": "POS-1042",
  "items": [
    {"product_id": 5, "quantity": 2, "unit_price": 1.20},
    {"product_id": 8, "quantity": 1, "unit_price": 3.50}
  ]
}
```

Stock is updated automatically:
- `sale` → decreases stock
- `purchase` → increases stock
- `adjustment` → sets stock to the given quantity

---

## Offline Mode (Mobile)

The mobile app uses **SQLite** (via `sqflite`) as a local cache and supports full offline operation for read actions and transactional writes.

| Action | Online | Offline |
|--------|--------|---------|
| View dashboard | Live from API | Served from SQLite cache |
| Browse products | Live from API | Served from SQLite cache |
| Browse transactions | Live from API | Served from SQLite cache |
| Record sale / restock | Sent immediately | Queued in SQLite |
| Add new product | Sent immediately | ✗ Not supported offline |
| Create category | Sent immediately | ✗ Not supported offline |

**Queue flush:** When the app detects it has reconnected (via `connectivity_plus`), it automatically flushes pending transactions in order and runs a delta sync to refresh stock levels. The app bar shows a badge with the count of queued transactions.

**Optimistic updates:** When a transaction is queued offline, stock quantities in the local cache are updated immediately so the shopkeeper sees accurate levels while offline.

---

## Database Schema

| Table | Key columns |
|-------|-------------|
| `shops` | `is_admin`, `is_active` flags |
| `categories` | `shop_id` FK, `color` (hex) |
| `products` | `shop_id` + `category_id` FK, stock levels, `updated_at` for delta sync |
| `transactions` | `shop_id`, `transaction_type` enum |
| `transaction_items` | per-line quantities and prices |

### Migrating an existing database

If upgrading from a version before categories were introduced:

```bash
psql -U postgres -d stocktracker -f migrate_categories.sql
```

---

## Security Notes

| Concern | Approach |
|---------|----------|
| Web passwords | Argon2id via `passlib[argon2]` |
| Web sessions | Signed server-side cookies via `itsdangerous` |
| Mobile auth | Short-lived JWT (7 days), `python-jose` |
| Admin guard | `require_admin()` on all `/admin` routes |
| Mobile guard | JWT decoded on every `/api/*` request; admin accounts blocked |
| Shop isolation | All queries filter by `shop_id` from session / token |
| Self-registration | Disabled — admin creates all accounts |
| Barcode lookup | Server-side proxy — no CORS or API keys needed |

---

## Production Deployment

```bash
# Backend
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Mobile — build release APK
cd mobile && flutter build apk --release
```

- Put Nginx in front for HTTPS (required for camera access on real devices)
- Set a strong random `SECRET_KEY` in `.env`
- Override `ADMIN_PASSWORD` via env before first startup
- Ensure `static/js/html5-qrcode.min.js` is present
- Restrict direct PostgreSQL access to the app server only
