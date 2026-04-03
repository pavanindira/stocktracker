import subprocess
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from database import engine
import models
import os
from dotenv import load_dotenv

from routers.auth_router import router as auth_router
from routers.dashboard import router as dashboard
from routers.products import router as products
from routers.transactions import router as transactions
from routers.reports import router as reports
from routers.admin import router as admin
from routers.categories import router as categories
from routers.api import router as api
from routers.team import router as team
from routers.labels import router as labels
from routers.import_csv import router as import_csv
from routers.receipt_public import router as receipt_public
from routers.suppliers import router as suppliers
from routers.stocktake import router as stocktake

from routers.audit_router import router as audit_router
from routers.csrf import CSRFProtectionMiddleware
from seed import seed_admin

load_dotenv()


def run_migrations():
    """Run Alembic migrations. Works for both Docker and non-Docker setups."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Database migrations applied successfully")
        else:
            print(f"⚠️ Migration warning: {result.stderr}")
    except FileNotFoundError:
        # Alembic not installed - might be in a different environment
        print("⚠️ Alembic not found - skipping migrations")
    except Exception as e:
        print(f"⚠️ Migration error: {e}")


# Schema is managed by Alembic — run: alembic upgrade head
# models.Base.metadata.create_all(bind=engine)  # kept for reference only
run_migrations()
seed_admin()

# ── Background scheduler (push notifications + email digest) ─────────────────
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import notifications as notif

scheduler = BackgroundScheduler(timezone="UTC")
DIGEST_HOUR = max(0, min(23, int(os.getenv("DIGEST_HOUR", "8"))))

@asynccontextmanager
async def lifespan(app):
    scheduler.add_job(notif.check_low_stock_and_expiry, "interval", hours=6,
                      id="push_alerts", replace_existing=True)
    scheduler.add_job(notif.send_daily_digest, "cron", hour=DIGEST_HOUR,
                      id="email_digest", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="StockTracker", description="Multi-shop stock management system")

# Only run scheduler if explicitly enabled - prevents duplicate jobs with multiple workers
if os.getenv("RUN_SCHEDULER", "true").lower() == "true":
    app.router.lifespan_context = lifespan

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

@app.get("/health", include_in_schema=False)
async def health():
    """Docker / load-balancer health check endpoint."""
    return {"status": "ok"}

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(team.router)
app.include_router(labels.router)
app.include_router(import_csv.router)
app.include_router(receipt_public.router)
app.include_router(suppliers.router)
app.include_router(stocktake.router)

app.include_router(audit_router.router)
app.include_router(admin.router)
app.include_router(api.router)
