from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.csrf import CSRFMiddleware
from database import engine
import models
import os
from dotenv import load_dotenv

from routers import auth_router, dashboard, products, transactions, reports

load_dotenv()

# Create all tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="StockTracker", description="Multi-shop stock management system")

# Session middleware (secret key from env - required in production)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required. Set it in .env file.")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# CSRF middleware
app.add_middleware(
    CSRFMiddleware,
    secret_key=SECRET_KEY,
    safe_origins=[]  # Configure appropriately for production
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(transactions.router)
app.include_router(reports.router)
