-- migrate_suppliers_stocktake.sql
-- Adds supplier management and stocktake / physical count tables.
-- Safe to re-run (IF NOT EXISTS throughout).

BEGIN;

-- ── 1. Suppliers ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suppliers (
    id             SERIAL PRIMARY KEY,
    shop_id        INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name           VARCHAR(200) NOT NULL,
    contact_name   VARCHAR(200),
    phone          VARCHAR(50),
    email          VARCHAR(200),
    website        VARCHAR(300),
    notes          TEXT,
    lead_time_days INTEGER DEFAULT 3,
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_suppliers_shop_id ON suppliers(shop_id);

-- ── 2. Link products → preferred supplier ────────────────────────────────────
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS supplier_id      INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS reorder_quantity FLOAT DEFAULT 0;

-- ── 3. Link purchase transactions → supplier ─────────────────────────────────
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL;

-- ── 4. Stocktakes ─────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE stocktake_status AS ENUM ('draft', 'in_progress', 'completed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS stocktakes (
    id           SERIAL PRIMARY KEY,
    shop_id      INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name         VARCHAR(200) NOT NULL,
    status       stocktake_status DEFAULT 'draft',
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_stocktakes_shop_id ON stocktakes(shop_id);

-- ── 5. Stocktake line items ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stocktake_items (
    id               SERIAL PRIMARY KEY,
    stocktake_id     INTEGER NOT NULL REFERENCES stocktakes(id) ON DELETE CASCADE,
    product_id       INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    system_quantity  FLOAT NOT NULL,
    counted_quantity FLOAT,           -- NULL = not yet counted
    notes            TEXT
);

CREATE INDEX IF NOT EXISTS ix_stocktake_items_stocktake_id
    ON stocktake_items(stocktake_id);

COMMIT;

SELECT 'Suppliers + stocktake migration complete' AS status;
