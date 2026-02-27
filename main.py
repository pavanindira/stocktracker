from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from database import engine
import models
import os
from dotenv import load_dotenv

from routers import auth_router, dashboard, products, transactions, reports

load_dotenv()

# Create all tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="StockTracker", description="Multi-shop stock management system")

# Session middleware (secret key from env)
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(transactions.router)
app.include_router(reports.router)
