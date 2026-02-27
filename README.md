# StockTracker

A multi-shop stock inventory management web application built with **FastAPI**, **Jinja2**, and **PostgreSQL**.

## Features

- **Multi-shop support** — Each shop registers separately and has isolated data
- **Product management** — Add, edit, delete products with SKU, category, pricing, and units
- **Stock tracking** — Real-time stock levels with low-stock alerts on the dashboard
- **Sales & purchases** — Record transactions with multiple line items; stock updates automatically
- **Stock adjustments** — Manually correct stock quantities
- **Reports** — Sales summary, top products, stock status with custom date ranges
- **CSV exports** — Export stock inventory and transactions to CSV

---

## Project Structure

```
stocktracker/
├── main.py                  # FastAPI app entry point
├── database.py              # SQLAlchemy engine & session
├── models.py                # ORM models (Shop, Product, Transaction, TransactionItem)
├── auth.py                  # Password hashing & session helpers
├── routers/
│   ├── auth_router.py       # Login, logout, register
│   ├── dashboard.py         # Dashboard overview
│   ├── products.py          # Product CRUD
│   ├── transactions.py      # Sales, purchases, adjustments
│   └── reports.py           # Reports + CSV export
├── templates/               # Jinja2 HTML templates
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── products/
│   │   ├── index.html
│   │   └── form.html
│   ├── transactions/
│   │   ├── index.html
│   │   ├── form.html
│   │   └── detail.html
│   └── reports/
│       └── index.html
├── static/                  # Static assets (CSS, JS, images)
├── requirements.txt
└── .env.example
```

---

## Setup Instructions

### 1. Prerequisites

- Python 3.10+
- PostgreSQL running locally (or remote)

### 2. Clone and set up environment

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```
DATABASE_URL=postgresql://YOUR_USER:YOUR_PASSWORD@localhost:5432/stocktracker
SECRET_KEY=replace-with-a-long-random-string
```

### 4. Create the database

```bash
# Connect to PostgreSQL and create the database
psql -U postgres
CREATE DATABASE stocktracker;
\q
```

The tables will be created automatically when you first start the app.

### 5. Run the application

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit: **http://localhost:8000**

---

## Usage

1. **Register** your shop at `/register`
2. **Log in** at `/login`
3. **Add products** via Products → New Product
4. **Record transactions**:
   - Sales reduce stock
   - Purchases increase stock
   - Adjustments set stock to an absolute value
5. **Monitor** low-stock alerts on the Dashboard
6. **Export** CSV reports from the Reports page

---

## Database Schema

| Table | Description |
|-------|-------------|
| `shops` | Shop accounts with username/password |
| `products` | Products per shop with stock levels and pricing |
| `transactions` | Sales, purchases, adjustments |
| `transaction_items` | Individual line items per transaction |

---

## Production Deployment Notes

- Set a strong `SECRET_KEY` in `.env`
- Use a production WSGI/ASGI server (e.g., Gunicorn + Uvicorn workers)
- Set up PostgreSQL with proper credentials
- Consider adding HTTPS via a reverse proxy (Nginx)
- Run with: `gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker`
