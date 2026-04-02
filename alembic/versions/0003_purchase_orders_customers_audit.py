"""Add purchase orders, customers, audit log, device tokens, return transaction type

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-01 00:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extend TransactionType enum with RETURN ───────────────────────────────
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'return'")

    # ── Extend POStatus enum (new) ────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE postatus AS ENUM
                ('draft','sent','partially_received','completed','cancelled');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # ── customers ─────────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id",             sa.Integer(),   primary_key=True),
        sa.Column("shop_id",        sa.Integer(),   sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",           sa.String(200), nullable=False),
        sa.Column("phone",          sa.String(50),  nullable=True),
        sa.Column("email",          sa.String(200), nullable=True),
        sa.Column("notes",          sa.Text(),      nullable=True),
        sa.Column("loyalty_points", sa.Float(),     server_default="0"),
        sa.Column("is_active",      sa.Boolean(),   server_default="true"),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_customers_shop_id", "customers", ["shop_id"])

    # ── purchase_orders ───────────────────────────────────────────────────────
    op.create_table(
        "purchase_orders",
        sa.Column("id",                sa.Integer(),   primary_key=True),
        sa.Column("shop_id",           sa.Integer(),   sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id",       sa.Integer(),   sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status",            sa.Enum("draft","sent","partially_received","completed","cancelled", name="postatus"), server_default="draft"),
        sa.Column("reference",         sa.String(100), nullable=True),
        sa.Column("notes",             sa.Text(),      nullable=True),
        sa.Column("expected_delivery", sa.Date(),      nullable=True),
        sa.Column("total_amount",      sa.Float(),     server_default="0"),
        sa.Column("created_at",        sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("sent_at",           sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at",      sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_purchase_orders_shop_id", "purchase_orders", ["shop_id"])

    # ── purchase_order_items ──────────────────────────────────────────────────
    op.create_table(
        "purchase_order_items",
        sa.Column("id",                sa.Integer(), primary_key=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id",        sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity_ordered",  sa.Float(),   nullable=False),
        sa.Column("quantity_received", sa.Float(),   server_default="0"),
        sa.Column("unit_price",        sa.Float(),   server_default="0"),
        sa.Column("lot_number",        sa.String(100), nullable=True),
        sa.Column("expiry_date",       sa.Date(),    nullable=True),
    )
    op.create_index("ix_po_items_purchase_order_id", "purchase_order_items", ["purchase_order_id"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id",          sa.Integer(),   primary_key=True),
        sa.Column("shop_id",     sa.Integer(),   sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_name",  sa.String(200), nullable=False),
        sa.Column("actor_role",  sa.String(50),  nullable=True),
        sa.Column("action",      sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id",   sa.Integer(),   nullable=True),
        sa.Column("description", sa.Text(),      nullable=True),
        sa.Column("before_val",  sa.Text(),      nullable=True),
        sa.Column("after_val",   sa.Text(),      nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_logs_shop_id",   "audit_logs", ["shop_id"])
    op.create_index("ix_audit_logs_entity",    "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_created_at","audit_logs", ["created_at"])

    # ── device_tokens ─────────────────────────────────────────────────────────
    op.create_table(
        "device_tokens",
        sa.Column("id",         sa.Integer(),    primary_key=True),
        sa.Column("shop_id",    sa.Integer(),    sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token",      sa.String(512),  nullable=False),
        sa.Column("platform",   sa.String(20),   nullable=True),
        sa.Column("actor_name", sa.String(200),  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_tokens_token",   "device_tokens", ["token"])
    op.create_index("ix_device_tokens_shop_id", "device_tokens", ["shop_id"])

    # ── transactions — add customer_id + return_of_id ─────────────────────────
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column(
            "customer_id", sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
        ))
        batch_op.add_column(sa.Column(
            "return_of_id", sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
        ))
        # Add indexes for performance
        batch_op.create_index("ix_transactions_customer_id", ["customer_id"])
        batch_op.create_index("ix_transactions_return_of_id", ["return_of_id"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_return_of_id")
        batch_op.drop_index("ix_transactions_customer_id")
        batch_op.drop_column("return_of_id")
        batch_op.drop_column("customer_id")

    op.drop_table("device_tokens")
    op.drop_table("audit_logs")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("customers")
    op.execute("DROP TYPE IF EXISTS postatus")
