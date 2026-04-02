"""Initial schema — full baseline

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

Captures the complete StockTracker schema at the point Alembic was
introduced (all tables from the manual SQL migration files).
New installs run only this file + subsequent revisions.
Existing installs should run:  alembic stamp 0001
then apply only newer revisions with:  alembic upgrade head
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ENUMS ────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE IF NOT EXISTS userrole AS ENUM ('owner', 'manager', 'cashier')")
    op.execute("CREATE TYPE IF NOT EXISTS transactiontype AS ENUM ('purchase', 'sale', 'adjustment')")
    op.execute("CREATE TYPE IF NOT EXISTS discounttype AS ENUM ('none', 'percentage', 'fixed')")
    op.execute("CREATE TYPE IF NOT EXISTS stocktakestatus AS ENUM ('draft', 'in_progress', 'completed')")

    # ── shops ────────────────────────────────────────────────────────────────
    op.create_table(
        "shops",
        sa.Column("id",            sa.Integer(),     primary_key=True),
        sa.Column("name",          sa.String(100),   nullable=False),
        sa.Column("username",      sa.String(50),    unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255),   nullable=False),
        sa.Column("email",         sa.String(100),   unique=True, nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("is_active",     sa.Boolean(),     server_default="true"),
        sa.Column("is_admin",      sa.Boolean(),     server_default="false"),
    )
    op.create_index("ix_shops_username", "shops", ["username"], unique=True)

    # ── shop_sub_users ────────────────────────────────────────────────────────
    op.create_table(
        "shop_sub_users",
        sa.Column("id",            sa.Integer(),  primary_key=True),
        sa.Column("shop_id",       sa.Integer(),  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",          sa.String(200), nullable=False),
        sa.Column("username",      sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text(),      nullable=False),
        sa.Column("role",          sa.Enum("owner", "manager", "cashier", name="userrole"), nullable=False, server_default="cashier"),
        sa.Column("is_active",     sa.Boolean(),   server_default="true"),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_shop_sub_users_username", "shop_sub_users", ["username"], unique=True)
    op.create_index("ix_shop_sub_users_shop_id",  "shop_sub_users", ["shop_id"])

    # ── categories ───────────────────────────────────────────────────────────
    op.create_table(
        "categories",
        sa.Column("id",          sa.Integer(),  primary_key=True),
        sa.Column("shop_id",     sa.Integer(),  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",        sa.String(100), nullable=False),
        sa.Column("description", sa.Text(),      nullable=True),
        sa.Column("color",       sa.String(7),   server_default="#7c6af7"),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_categories_shop_id", "categories", ["shop_id"])

    # ── suppliers ────────────────────────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column("id",             sa.Integer(),   primary_key=True),
        sa.Column("shop_id",        sa.Integer(),   sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",           sa.String(200), nullable=False),
        sa.Column("contact_name",   sa.String(200), nullable=True),
        sa.Column("phone",          sa.String(50),  nullable=True),
        sa.Column("email",          sa.String(200), nullable=True),
        sa.Column("website",        sa.String(300), nullable=True),
        sa.Column("notes",          sa.Text(),      nullable=True),
        sa.Column("lead_time_days", sa.Integer(),   server_default="3"),
        sa.Column("is_active",      sa.Boolean(),   server_default="true"),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_suppliers_shop_id", "suppliers", ["shop_id"])

    # ── products ─────────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id",                  sa.Integer(),  primary_key=True),
        sa.Column("shop_id",             sa.Integer(),  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id",         sa.Integer(),  sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_id",         sa.Integer(),  sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name",                sa.String(200), nullable=False),
        sa.Column("sku",                 sa.String(100), nullable=True),
        sa.Column("description",         sa.Text(),      nullable=True),
        sa.Column("unit",                sa.String(50),  server_default="pcs"),
        sa.Column("cost_price",          sa.Float(),     server_default="0"),
        sa.Column("selling_price",       sa.Float(),     server_default="0"),
        sa.Column("stock_quantity",      sa.Float(),     server_default="0"),
        sa.Column("low_stock_threshold", sa.Float(),     server_default="10"),
        sa.Column("default_expiry_date", sa.Date(),      nullable=True),
        sa.Column("reorder_quantity",    sa.Float(),     server_default="0"),
        sa.Column("created_at",          sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True), onupdate=sa.text("now()"), nullable=True),
        sa.Column("is_active",           sa.Boolean(),   server_default="true"),
    )
    op.create_index("ix_products_shop_id", "products", ["shop_id"])

    # ── product_batches ──────────────────────────────────────────────────────
    op.create_table(
        "product_batches",
        sa.Column("id",          sa.Integer(), primary_key=True),
        sa.Column("product_id",  sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_number",  sa.String(100), nullable=True),
        sa.Column("quantity",    sa.Float(),     nullable=False, server_default="0"),
        sa.Column("expiry_date", sa.Date(),      nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("notes",       sa.Text(),      nullable=True),
    )
    op.create_index("ix_product_batches_product_id",  "product_batches", ["product_id"])
    op.create_index("ix_product_batches_expiry_date", "product_batches", ["expiry_date"])

    # ── transactions ─────────────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id",               sa.Integer(),  primary_key=True),
        sa.Column("shop_id",          sa.Integer(),  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id",      sa.Integer(),  sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transaction_type", sa.Enum("purchase", "sale", "adjustment", "return", name="transactiontype"), nullable=False),
        sa.Column("reference",        sa.String(100), nullable=True),
        sa.Column("notes",            sa.Text(),      nullable=True),
        sa.Column("total_amount",     sa.Float(),     server_default="0"),
        sa.Column("tax_amount",       sa.Float(),     server_default="0"),
        sa.Column("tax_rate",         sa.Float(),     server_default="0"),
        sa.Column("discount_type",    sa.Enum("none", "percentage", "fixed", name="discounttype"), server_default="none"),
        sa.Column("discount_value",   sa.Float(),     server_default="0"),
        sa.Column("discount_amount",  sa.Float(),     server_default="0"),
        sa.Column("share_token",      sa.String(64),  unique=True, nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_transactions_shop_id",    "transactions", ["shop_id"])
    op.create_index("ix_transactions_share_token","transactions", ["share_token"], unique=True)

    # ── transaction_items ────────────────────────────────────────────────────
    op.create_table(
        "transaction_items",
        sa.Column("id",              sa.Integer(), primary_key=True),
        sa.Column("transaction_id",  sa.Integer(), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id",      sa.Integer(), sa.ForeignKey("products.id",     ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id",        sa.Integer(), sa.ForeignKey("product_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity",        sa.Float(),   nullable=False),
        sa.Column("unit_price",      sa.Float(),   nullable=False),
        sa.Column("discount_amount", sa.Float(),   server_default="0"),
        sa.Column("subtotal",        sa.Float(),   nullable=False),
        sa.Column("lot_number",      sa.String(100), nullable=True),
    )
    op.create_index("ix_transaction_items_transaction_id", "transaction_items", ["transaction_id"])

    # ── stocktakes ───────────────────────────────────────────────────────────
    op.create_table(
        "stocktakes",
        sa.Column("id",           sa.Integer(),  primary_key=True),
        sa.Column("shop_id",      sa.Integer(),  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",         sa.String(200), nullable=False),
        sa.Column("status",       sa.Enum("draft", "in_progress", "completed", name="stocktakestatus"), server_default="draft"),
        sa.Column("notes",        sa.Text(),      nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_stocktakes_shop_id", "stocktakes", ["shop_id"])

    # ── stocktake_items ──────────────────────────────────────────────────────
    op.create_table(
        "stocktake_items",
        sa.Column("id",               sa.Integer(), primary_key=True),
        sa.Column("stocktake_id",     sa.Integer(), sa.ForeignKey("stocktakes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id",       sa.Integer(), sa.ForeignKey("products.id",   ondelete="CASCADE"), nullable=False),
        sa.Column("system_quantity",  sa.Float(),   nullable=False),
        sa.Column("counted_quantity", sa.Float(),   nullable=True),
        sa.Column("notes",            sa.Text(),    nullable=True),
    )
    op.create_index("ix_stocktake_items_stocktake_id", "stocktake_items", ["stocktake_id"])


def downgrade() -> None:
    # Drop in reverse FK dependency order
    op.drop_table("stocktake_items")
    op.drop_table("stocktakes")
    op.drop_table("transaction_items")
    op.drop_table("transactions")
    op.drop_table("product_batches")
    op.drop_table("products")
    op.drop_table("suppliers")
    op.drop_table("categories")
    op.drop_table("shop_sub_users")
    op.drop_table("shops")
    op.execute("DROP TYPE IF EXISTS stocktakestatus")
    op.execute("DROP TYPE IF EXISTS discounttype")
    op.execute("DROP TYPE IF EXISTS transactiontype")
    op.execute("DROP TYPE IF EXISTS userrole")
