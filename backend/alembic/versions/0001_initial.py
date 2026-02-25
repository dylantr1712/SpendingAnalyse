"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-02-24 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
    )

    op.create_table(
        "raw_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("txn_date_raw", sa.String(length=32), nullable=False),
        sa.Column("amount_raw", sa.String(length=64), nullable=False),
        sa.Column("description_raw", sa.Text(), nullable=False),
        sa.Column("balance_raw", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "fct_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("description_raw", sa.Text(), nullable=False),
        sa.Column("merchant_key", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("is_income", sa.Boolean(), nullable=False),
        sa.Column("is_movement", sa.Boolean(), nullable=False),
        sa.Column("is_high_impact", sa.Boolean(), nullable=False),
        sa.Column("txn_hash", sa.String(length=64), nullable=False),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("user_id", "txn_hash", name="uq_fct_transactions_user_hash"),
    )

    op.create_table(
        "merchant_map",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("merchant_key", sa.String(length=255), primary_key=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "user_profile",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("reported_total_savings", sa.Float(), nullable=True),
    )

    op.create_table(
        "goals",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("goal_amount", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("goals")
    op.drop_table("user_profile")
    op.drop_table("merchant_map")
    op.drop_table("fct_transactions")
    op.drop_table("raw_transactions")
    op.drop_table("import_batches")
    op.drop_table("users")
