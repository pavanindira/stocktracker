-- migrate_roles.sql
-- Adds the shop_sub_users table and tax fields to transactions.
-- Run ONCE on an existing database.
-- Safe to re-run (uses IF NOT EXISTS / IF NOT EXISTS column checks).

BEGIN;

-- ── 1. Create UserRole enum type (if not exists) ──────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
        CREATE TYPE userrole AS ENUM ('owner', 'manager', 'cashier');
    END IF;
END$$;

-- ── 2. Create shop_sub_users table ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shop_sub_users (
    id            SERIAL PRIMARY KEY,
    shop_id       INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name          VARCHAR(200) NOT NULL,
    username      VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          userrole NOT NULL DEFAULT 'cashier',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_shop_sub_users_shop_id  ON shop_sub_users(shop_id);
CREATE INDEX IF NOT EXISTS ix_shop_sub_users_username ON shop_sub_users(username);

-- ── 3. Add tax columns to transactions ───────────────────────────────────
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS tax_amount FLOAT NOT NULL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS tax_rate   FLOAT NOT NULL DEFAULT 0.0;

COMMIT;

-- Verify
SELECT 'shop_sub_users created' AS status,
       count(*) AS existing_rows
FROM   shop_sub_users;
