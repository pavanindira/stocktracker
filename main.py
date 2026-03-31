import subprocess
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from database import engine
import models
import os
from dotenv import load_dotenv

from routers import auth_router, dashboard, products, transactions, reports, admin, categories, api, team, labels, import_csv, receipt_public, suppliers, stocktake
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

app = FastAPI(title="StockTracker", description="Multi-shop stock management system")

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
app.include_router(admin.router)
app.include_router(api.router)
