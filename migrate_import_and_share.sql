-- migrate_import_and_share.sql
-- Adds share_token to transactions and a product_import_log table.
-- Safe to re-run.

BEGIN;

-- ── 1. share_token on transactions ────────────────────────────────────────
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS share_token VARCHAR(64) UNIQUE;

CREATE INDEX IF NOT EXISTS ix_transactions_share_token
    ON transactions(share_token)
    WHERE share_token IS NOT NULL;

-- ── 2. Import log (optional audit trail) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS product_import_logs (
    id           SERIAL PRIMARY KEY,
    shop_id      INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    filename     VARCHAR(255),
    rows_total   INTEGER DEFAULT 0,
    rows_created INTEGER DEFAULT 0,
    rows_updated INTEGER DEFAULT 0,
    rows_skipped INTEGER DEFAULT 0,
    rows_failed  INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

COMMIT;

SELECT 'Migration complete' AS status;
