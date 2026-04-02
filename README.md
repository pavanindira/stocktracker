# StockTracker

A full-featured multi-shop inventory management system — **web app** (FastAPI + Jinja2) and **mobile app** (Flutter), backed by PostgreSQL with Docker deployment and full offline support.

---

## Feature Overview

### Web App

| Area | Features |
|------|----------|
| **Dashboard** | Live stats · low-stock widget · expiry alerts · monthly sales summary |
| **Products** | Full CRUD · SKU · category · pricing · units · low-stock threshold · default expiry · preferred supplier · reorder qty |
| **Barcode scan** | Browser camera scanner · Open Food Facts auto-fill |
| **CSV Import** | Drag-and-drop upload · row-by-row validation preview · skip or update duplicates · auto-create categories |
| **QR Label printing** | 50×30mm Dymo-style labels · QR code + name + price + SKU · PDF download |
| **Categories** | Colour-coded product categories |
| **Transactions** | Sales · purchases · adjustments · multi-item cart · tax rate · discounts · reference number |
| **Returns** | Reverse a sale · per-line quantity control · automatic restock · linked back to original transaction |
| **Discounts** | Order-level percentage or fixed-amount discounts · live breakdown on form |
| **FEFO** | Per-batch expiry tracking · oldest-expiry deducted first on sale · lot numbers on receipts |
| **Receipts** | PDF receipts · shareable public receipt link (no login required) |
| **Reports** | Date-range analytics · top sellers · stock status · expiry report · P&L report |
| **P&L Report** | Gross profit by period · product and category breakdown · margin % · discount impact |
| **Suppliers** | Supplier CRUD · link to products · purchase history · reorder suggestions |
| **Purchase Orders** | Draft → sent → receive delivery · per-line lot and expiry · auto-creates purchase transaction on receipt |
| **Customers** | Customer CRUD · transaction history · loyalty points · link sales to customers |
| **Stocktake** | Physical count sessions · AJAX count entry · variance review · auto adjustment transactions |
| **Audit Log** | Every stock-changing action recorded · filter by action and user · paginated view |
| **Team management** | Cashier / Manager sub-accounts per shop · role-based access |
| **Admin panel** | System-level shop management at `/admin` |

### Mobile App (Flutter — iOS & Android)

| Screen | Features |
|--------|----------|
| **Login** | Server URL + credentials · FCM token registration on login |
| **Dashboard** | Stats cards · low-stock list · expiry alerts |
| **Products** | Searchable list · category filter · low-stock toggle |
| **Scan** | Sale / Restock / Add Product modes · barcode scanner |
| **Cart** | Multi-item sale · customer picker · discount (% or fixed) · tax rate · expiry warning dialog |
| **Receipt** | Transaction summary · PDF download |
| **Transactions** | Paginated history · filter by type |
| **Categories** | Create / delete with colour picker |
| **Labels** | Product checklist · download 50×30mm PDF labels |
| **Import** | Pick CSV · preview rows · confirm import |
| **Suppliers** | Supplier list · Reorder tab with deficit view |
| **Stocktake** | Create count · per-item entry with live variance · commit |
| **Customers** | Searchable list · create customer · total spent and loyalty points |
| **Purchase Orders** | List with status badges · detail view with per-line received/outstanding quantities |
| **Audit Log** | Paginated log · action filter chips · colour-coded badges |
| **Team** | View / add / remove sub-accounts (owner only) |
| **Offline mode** | Full SQLite cache · sale and restock queue · auto-sync on reconnect |
| **Push notifications** | FCM alerts for low stock and expiry (Firebase required) |

---

## Role Permissions

| Feature | Cashier | Manager | Owner |
|---------|:-------:|:-------:|:-----:|
| Record sales + returns | ✅ | ✅ | ✅ |
| Record purchases / adjustments | ❌ | ✅ | ✅ |
| Add / edit / import products | ❌ | ✅ | ✅ |
| Manage categories | ❌ | ✅ | ✅ |
| View reports / P&L / expiry | ❌ | ✅ | ✅ |
| See cost prices | ❌ | ✅ | ✅ |
| Manage suppliers / purchase orders / stocktake | ❌ | ✅ | ✅ |
| View audit log | ❌ | ✅ | ✅ |
| Manage customers | ✅ | ✅ | ✅ |
| Manage team members | ❌ | ❌ | ✅ |

> System Admin accounts can only access `/admin` and cannot log in to the mobile app.

---

## Project Structure

```
stocktracker/
│
├── main.py                            # FastAPI entry point · router registration · APScheduler
├── database.py                        # SQLAlchemy engine & session factory
├── models.py                          # All ORM models (see Database Schema)
├── auth.py                            # Password hashing, session helpers, role guards
├── audit.py                           # Audit log helper (log_action / log_action_api)
├── fefo.py                            # First-Expiry First-Out engine
├── notifications.py                   # FCM push + SMTP daily digest (APScheduler jobs)
├── seed.py                            # Seeds default admin on first startup
│
├── routers/
│   ├── __init__.py
│   ├── auth_router.py                 # Web login / logout
│   ├── admin.py                       # /admin — system-level shop management
│   ├── dashboard.py                   # Shop dashboard
│   ├── categories.py                  # Category CRUD (web)
│   ├── products.py                    # Product CRUD + barcode lookup (web)
│   ├── transactions.py                # Transaction CRUD + returns (web)
│   ├── reports.py                     # Reports + expiry report + P&L + CSV exports
│   ├── team.py                        # Team / sub-user management (owner only)
│   ├── labels.py                      # QR label PDF generation
│   ├── import_csv.py                  # Bulk CSV product import (web)
│   ├── receipt_public.py              # Public receipt pages — no auth required
│   ├── suppliers.py                   # Supplier CRUD + reorder suggestions
│   ├── stocktake.py                   # Stocktake flow: create → count → review → commit
│   ├── purchase_orders.py             # PO CRUD + receive delivery
│   ├── customers.py                   # Customer CRUD + history
│   ├── audit_router.py                # Audit log viewer
│   └── api.py                         # Mobile REST API — all /api/* JWT endpoints
│
├── templates/                         # Jinja2 HTML templates
│   ├── base.html                      # Master layout with role-aware sidebar nav
│   ├── login.html
│   ├── dashboard.html
│   ├── receipt_public.html
│   ├── admin/
│   ├── categories/
│   ├── products/
│   │   ├── index.html · form.html · scan.html · labels.html · import.html · import_done.html
│   ├── transactions/
│   │   ├── index.html · form.html · detail.html · return.html
│   ├── reports/
│   │   ├── index.html · expiry.html · profit.html
│   ├── team/
│   ├── suppliers/
│   │   ├── index.html · form.html · detail.html · reorder.html
│   ├── stocktake/
│   │   ├── index.html · new.html · count.html · review.html · done.html
│   ├── purchase_orders/
│   │   ├── index.html · form.html · detail.html · receive.html
│   ├── customers/
│   │   ├── index.html · form.html · detail.html
│   └── audit/
│       └── index.html
│
├── static/
│   └── js/
│       └── html5-qrcode.min.js        # Barcode scanner library (download separately)
│
├── mobile/
│   ├── pubspec.yaml
│   ├── android/app/src/main/
│   │   └── AndroidManifest.xml        # Camera + FCM permissions + setup notes
│   ├── ios/Runner/
│   │   └── Info.plist                 # Camera + FCM background modes + setup notes
│   └── lib/
│       ├── main.dart                  # Firebase init (graceful fallback if unconfigured)
│       ├── theme.dart
│       ├── services/
│       │   ├── api_service.dart       # All HTTP calls to the backend
│       │   ├── auth_service.dart      # Token, role, serverUrl · FCM unregister on logout
│       │   ├── local_db.dart          # SQLite cache for offline support
│       │   └── sync_service.dart      # Delta sync + offline queue flush
│       └── screens/
│           ├── login_screen.dart      # FCM token registration on login
│           ├── main_shell.dart        # Bottom nav · role-based tabs · offline chip
│           ├── dashboard_screen.dart
│           ├── products_screen.dart
│           ├── scan_screen.dart
│           ├── cart_screen.dart       # Customer picker · discount row · expiry warning
│           ├── receipt_screen.dart
│           ├── transactions_screen.dart
│           ├── transaction_sheet.dart
│           ├── categories_screen.dart
│           ├── add_product_sheet.dart
│           ├── labels_screen.dart
│           ├── import_screen.dart
│           ├── team_screen.dart
│           ├── suppliers_screen.dart
│           ├── stocktake_screen.dart
│           ├── customers_screen.dart  # Searchable list · create · total spent · points
│           ├── purchase_orders_screen.dart  # PO list · detail with per-line quantities
│           └── audit_screen.dart      # Paginated log · action filter chips
│
├── alembic/
│   ├── env.py                         # Wired to DATABASE_URL + Base.metadata
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_initial_schema.py     # Full baseline — all tables
│       ├── 0002_add_discounts.py      # Discount columns on transactions
│       └── 0003_purchase_orders_customers_audit.py  # POs, customers, audit, device tokens, returns
│
├── alembic.ini
├── Dockerfile                         # Multi-stage Python 3.12 slim image
├── docker-compose.yml                 # Postgres + App + Nginx — one-command deploy
├── entrypoint.sh                      # Wait for DB → alembic upgrade head → seed → uvicorn
├── .dockerignore
├── nginx/
│   └── nginx.conf                     # Reverse proxy + static file serving
│
├── requirements.txt
└── .env.example
```

---

## Database Schema

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `shops` | Shop accounts | `is_admin`, `is_active` |
| `shop_sub_users` | Cashier / Manager accounts | `shop_id`, `role` enum |
| `categories` | Product categories | `shop_id`, `color` |
| `products` | Inventory items | `shop_id`, `supplier_id`, `default_expiry_date`, `reorder_quantity` |
| `product_batches` | Per-restock lots (FEFO) | `product_id`, `expiry_date`, `quantity`, `lot_number` |
| `transactions` | Sales / purchases / adjustments / returns | `shop_id`, `transaction_type`, `supplier_id`, `customer_id`, `return_of_id`, `discount_type`, `share_token` |
| `transaction_items` | Line items | `transaction_id`, `product_id`, `batch_id`, `lot_number`, `discount_amount` |
| `suppliers` | Supplier directory | `shop_id`, `lead_time_days` |
| `purchase_orders` | Formal POs | `shop_id`, `supplier_id`, `status` (draft→sent→partially_received→completed) |
| `purchase_order_items` | PO line items | `purchase_order_id`, `quantity_ordered`, `quantity_received` |
| `customers` | Customer directory | `shop_id`, `loyalty_points`, `is_active` |
| `stocktakes` | Physical count sessions | `shop_id`, `status` (draft→in_progress→completed) |
| `stocktake_items` | Per-product counts | `stocktake_id`, `system_quantity`, `counted_quantity` |
| `audit_logs` | Action history | `shop_id`, `actor_name`, `action`, `entity_type`, `entity_id`, `before_val`, `after_val` |
| `device_tokens` | FCM push targets | `shop_id`, `token`, `platform` |

---

## Backend Setup

### Option A — Docker (recommended)

```bash
cp .env.example .env          # fill in SECRET_KEY, POSTGRES_PASSWORD, ADMIN_PASSWORD

# Download barcode scanner JS library
curl -L "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js" \
     -o static/js/html5-qrcode.min.js

docker compose up -d
```

The entrypoint script automatically waits for Postgres → runs `alembic upgrade head` → seeds the admin → starts Uvicorn.

```
[seed] Default admin created — username: 'admin' | password: 'Admin@1234'
[seed] ⚠  Change the admin password immediately via /admin
```

**Useful commands:**

```bash
docker compose logs -f app              # tail app logs
docker compose exec app alembic history # show migration history
docker compose exec app alembic upgrade head  # apply new migrations after git pull
docker compose down                     # stop (data preserved in volumes)
docker compose down -v                  # stop AND wipe all data
```

---

### Option B — Bare metal

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set DATABASE_URL=postgresql://user:pass@localhost:5432/stocktracker
# Set SECRET_KEY, ADMIN_PASSWORD

curl -L "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js" \
     -o static/js/html5-qrcode.min.js

psql -U postgres -c "CREATE DATABASE stocktracker;"
alembic upgrade head
python3 seed.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Upgrading from manual SQL migrations (pre-Alembic):**

```bash
alembic stamp 0001      # tell Alembic the baseline is already applied
alembic upgrade head    # runs 0002, 0003, and any future migrations
```

---

## Mobile App Setup

### Prerequisites
- Flutter SDK 3.x — [flutter.dev](https://flutter.dev/docs/get-started/install)
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

On the login screen enter the **Server URL**:

| Setup | Example |
|-------|---------|
| Same Wi-Fi | `http://192.168.1.100:8000` |
| LAN hostname | `http://stocktracker.local:8000` |
| Production | `https://yourdomain.com` |

### Enabling push notifications (optional)

1. Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com)
2. Add an Android app (and/or iOS app) to the project
3. **Android:** download `google-services.json` → place in `mobile/android/app/`
4. **iOS:** download `GoogleService-Info.plist` → add to `ios/Runner/` via Xcode
5. Copy the FCM **Server key** from Firebase console → paste into `.env` as `FCM_SERVER_KEY`
6. See detailed setup comments inside `AndroidManifest.xml` and `Info.plist`

Push notifications are completely optional. The app functions normally without them.

---

## REST API Reference

All endpoints at `/api`. Auth uses **Bearer JWT** tokens (7-day expiry).

### Authentication · `POST /api/auth/login`

```json
{ "access_token": "<jwt>", "token_type": "bearer",
  "shop_id": 3, "shop_name": "Green Valley Store",
  "role": "owner", "user_name": "owner" }
```

### Core endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dashboard` | Stats, low-stock, expiry alerts |
| `GET` | `/api/sync` | Delta product+category sync for offline cache |
| `GET/POST` | `/api/products` | List (with filters) / create |
| `GET` | `/api/products/barcode/{barcode}` | Barcode lookup |
| `GET` | `/api/products/{id}/batches` | FEFO batches for a product |
| `GET/POST` | `/api/transactions` | List / create (sale/purchase/adjustment) |
| `GET` | `/api/transactions/{id}` | Detail with line items |
| `POST` | `/api/transactions/{id}/share` | Generate shareable receipt URL |
| `GET` | `/api/transactions/{id}/receipt` | Download PDF receipt |
| `POST` | `/api/transactions/{id}/return` | Create return against a sale |
| `GET/POST` | `/api/customers` | List / create customers |
| `GET` | `/api/purchase-orders` | List purchase orders |
| `GET` | `/api/purchase-orders/{id}` | PO detail with line items |
| `GET/POST` | `/api/stocktakes` | List / create stocktake sessions |
| `GET` | `/api/stocktakes/{id}/items` | Stocktake line items |
| `PATCH` | `/api/stocktakes/{id}/items/{item_id}` | Save counted quantity |
| `POST` | `/api/stocktakes/{id}/commit` | Apply variances + complete |
| `GET` | `/api/suppliers` | List suppliers |
| `GET` | `/api/suppliers/reorder` | Low-stock products with supplier info |
| `GET` | `/api/expiry` | Expired + expiring-soon batches |
| `GET` | `/api/reports/profit` | P&L report (period or date range) |
| `GET` | `/api/labels` | Download QR label PDF (`?ids=1,2,3`) |
| `POST` | `/api/products/import` | CSV bulk import |
| `GET` | `/api/audit` | Paginated audit log |
| `POST/DELETE` | `/api/device-token` | Register / unregister FCM token |
| `GET/POST` | `/api/categories` | List / create categories |
| `DELETE` | `/api/categories/{id}` | Delete category |
| `GET/POST` | `/api/team` | List / create team members (owner only) |
| `DELETE` | `/api/team/{id}` | Remove team member |

---

## Discounts

Applied at order level on any transaction. Two types:

- **Percentage** — e.g. 10% off subtotal. Computed amount shown live on form.
- **Fixed** — e.g. $5.00 off. Capped at subtotal.

Flow: `subtotal − discount = discounted subtotal → + tax → total`. P&L report deducts discounts from revenue so margin figures are accurate.

---

## Returns

Click **↩ Create Return** on any sale detail page (managers only). Select return quantities per line item — stock is restocked immediately and a `RETURN` type transaction is created linked back to the original sale via `return_of_id`.

---

## Purchase Orders

**Web flow:** Create PO (pre-fills low-stock products for a supplier) → Mark as Sent → Receive Delivery (enter qty + lot + expiry per line) → Stock updated, FEFO batch created, PO marked completed or partially received.

**Statuses:** `draft` → `sent` → `partially_received` → `completed` (or `cancelled` at any point).

---

## FEFO — First-Expiry First-Out

Every purchase creates a `ProductBatch` with quantity, expiry date, and optional lot number. Every sale calls `fefo.deduct_fefo()` which drains batches in ascending expiry date order. Lot numbers are snapshotted on `TransactionItem` and shown on receipts.

Expiry warnings appear on: Dashboard · Products list · Expiry Report · Mobile cart (dialog before confirm).

---

## Audit Log

Every stock-changing operation writes to `audit_logs`: actor name + role, action type, entity type + ID, human-readable description, and optional before/after JSON snapshots. Accessible at `/audit` (web) and `GET /api/audit` (mobile).

Logged actions include: `SALE`, `PURCHASE`, `ADJUSTMENT`, `RETURN`, `CREATE_PO`, `SEND_PO`, `RECEIVE_PO`, `CANCEL_PO`, `EDIT_PO`, `CREATE_CUSTOMER`, `EDIT_CUSTOMER`, `DELETE_CUSTOMER`.

---

## Push Notifications

When `FCM_SERVER_KEY` is set in `.env`, the backend sends push notifications via Firebase FCM:

- **Every 6 hours:** low stock check — notifies all registered devices for shops with products at or below threshold
- **Every 6 hours:** expiry check — notifies for expired or expiring-soon batches

Device tokens are registered when users log in on mobile and unregistered on logout.

---

## Daily Email Digest

When SMTP is configured, a daily HTML email is sent to each shop's registered email address at `DIGEST_HOUR` UTC. It includes yesterday's sales total, low-stock products table, and expiry alerts table. Shops with nothing to report are skipped.

---

## Offline Mode (Mobile)

| Action | Online | Offline |
|--------|--------|---------|
| View dashboard / products / transactions | Live API | SQLite cache |
| Record sale / restock | Sent immediately | Queued · stock updated optimistically |
| Add product / category | Sent immediately | ❌ Not supported |

On reconnect, `sync_service.dart` flushes the queue in order then runs a delta sync.

---

## Security

| Concern | Approach |
|---------|----------|
| Web passwords | Argon2id via `passlib[argon2]` |
| Web sessions | Signed server-side cookies via `itsdangerous` |
| Mobile auth | 7-day JWT · admin accounts blocked from mobile |
| Role enforcement | Every route checks session role |
| Shop isolation | All queries filter by `shop_id` from session / JWT |
| Public receipts | 48-char random hex tokens · no cost prices exposed |
| Self-registration | Disabled — admin creates all accounts |

---

## Production Deployment

```bash
# Docker — recommended
cp .env.example .env    # set strong SECRET_KEY, POSTGRES_PASSWORD, ADMIN_PASSWORD
docker compose up -d --build

# After updates
git pull && docker compose up -d --build

# Mobile release builds
cd mobile
flutter build apk --release    # Android
flutter build ipa               # iOS
```

### Enabling HTTPS

1. `certbot certonly --standalone -d yourdomain.com`
2. Uncomment HTTPS blocks in `nginx/nginx.conf`
3. Set `HTTPS_PORT=443` in `.env`
4. `docker compose restart nginx`

### Pre-launch checklist

- [ ] `SECRET_KEY` is a 64-char random hex string
- [ ] `POSTGRES_PASSWORD` and `ADMIN_PASSWORD` are strong unique values
- [ ] HTTPS configured (required for camera access and secure cookies)
- [ ] Default admin password changed at `/admin` after first login
- [ ] `static/js/html5-qrcode.min.js` downloaded and present
- [ ] Postgres port `5432` not publicly exposed
- [ ] Backups configured for `postgres_data` Docker volume
- [ ] (Optional) `FCM_SERVER_KEY` set for push notifications
- [ ] (Optional) `SMTP_HOST` + credentials set for email digest
