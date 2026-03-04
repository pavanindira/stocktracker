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

models.Base.metadata.create_all(bind=engine)
seed_admin()

app = FastAPI(title="StockTracker", description="Multi-shop stock management system")

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

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
