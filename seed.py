"""
Seed script: ensures the default system admin account exists.
Called automatically from main.py on startup.
"""
import os
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from auth import hash_password

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@1234")
ADMIN_NAME = os.getenv("ADMIN_NAME", "System Administrator")


def seed_admin():
    db: Session = SessionLocal()
    try:
        existing = db.query(models.Shop).filter(
            models.Shop.username == ADMIN_USERNAME
        ).first()

        if not existing:
            admin = models.Shop(
                name=ADMIN_NAME,
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                is_admin=True,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(f"[seed] Default admin created — username: '{ADMIN_USERNAME}' | password: '{ADMIN_PASSWORD}'")
            print("[seed] ⚠  Change the admin password immediately via the Admin panel!")
        else:
            if not existing.is_admin:
                existing.is_admin = True
                db.commit()
                print(f"[seed] Promoted '{ADMIN_USERNAME}' to admin.")
            else:
                print(f"[seed] Admin '{ADMIN_USERNAME}' already exists. Skipping.")
    finally:
        db.close()
