"""add user profile balances

Revision ID: 0002_user_profile_balances
Revises: 0001_initial
Create Date: 2026-02-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_user_profile_balances"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profile", sa.Column("bank_balance_override", sa.Float(), nullable=True))
    op.add_column("user_profile", sa.Column("savings_balance_override", sa.Float(), nullable=True))
    op.add_column("user_profile", sa.Column("investments_balance_override", sa.Float(), nullable=True))
    op.add_column("user_profile", sa.Column("balances_as_of", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profile", "balances_as_of")
    op.drop_column("user_profile", "investments_balance_override")
    op.drop_column("user_profile", "savings_balance_override")
    op.drop_column("user_profile", "bank_balance_override")
