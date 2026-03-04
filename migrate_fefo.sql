-- migrate_fefo.sql
-- Adds FEFO (First-Expiry First-Out) support:
--   • default_expiry_date on products
--   • product_batches table (per-lot expiry + quantity)
--   • batch_id + lot_number snapshot on transaction_items
-- Safe to re-run (IF NOT EXISTS throughout).

BEGIN;

-- ── 1. Default expiry on products ─────────────────────────────────────────
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS default_expiry_date DATE;

-- ── 2. Product batches ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_batches (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    lot_number  VARCHAR(100),
    quantity    FLOAT   NOT NULL DEFAULT 0,
    expiry_date DATE,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS ix_product_batches_product_id
    ON product_batches(product_id);

CREATE INDEX IF NOT EXISTS ix_product_batches_expiry
    ON product_batches(expiry_date)
    WHERE expiry_date IS NOT NULL;

-- ── 3. Batch reference on transaction items ───────────────────────────────
ALTER TABLE transaction_items
    ADD COLUMN IF NOT EXISTS batch_id    INTEGER REFERENCES product_batches(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS lot_number  VARCHAR(100);

-- ── 4. Seed batches from existing stock (no expiry, quantity = current stock) ─
-- This migrates existing products into a single "legacy" batch so FEFO
-- accounting starts from a clean slate.  Remove this block if you prefer
-- to start fresh with only new restocks tracked as batches.
INSERT INTO product_batches (product_id, lot_number, quantity, expiry_date, notes)
SELECT id, 'LEGACY', stock_quantity, default_expiry_date,
       'Auto-created from existing stock during FEFO migration'
FROM   products
WHERE  is_active = TRUE
  AND  stock_quantity > 0
  AND  NOT EXISTS (
      SELECT 1 FROM product_batches pb WHERE pb.product_id = products.id
  );

COMMIT;

SELECT 'FEFO migration complete' AS status,
       (SELECT count(*) FROM product_batches) AS total_batches;
