"""Add discount columns to transactions and transaction_items

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-01 00:00:00

For databases that existed before discounts were introduced.
New installs pick this up automatically via revision 0001.
Existing installs upgrading from manual SQL migrations: run
  alembic stamp 0001
  alembic upgrade head
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the discounttype enum if it doesn't exist yet
    # (new installs have it from 0001; upgrading installs may not)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE discounttype AS ENUM ('none', 'percentage', 'fixed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # transactions — order-level discount
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column(
            "discount_type",
            sa.Enum("none", "percentage", "fixed", name="discounttype"),
            server_default="none",
            nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "discount_value",
            sa.Float(),
            server_default="0",
            nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "discount_amount",
            sa.Float(),
            server_default="0",
            nullable=False,
        ))

    # transaction_items — line-level discount
    with op.batch_alter_table("transaction_items") as batch_op:
        batch_op.add_column(sa.Column(
            "discount_amount",
            sa.Float(),
            server_default="0",
            nullable=False,
        ))


def downgrade() -> None:
    with op.batch_alter_table("transaction_items") as batch_op:
        batch_op.drop_column("discount_amount")

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("discount_amount")
        batch_op.drop_column("discount_value")
        batch_op.drop_column("discount_type")
