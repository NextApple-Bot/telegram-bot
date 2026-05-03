"""Add index on daily_payments.sale_message_id

Revision ID: 009
Revises: 008
Create Date: 2026-04-11 14:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'idx_daily_payments_sale_message_id',
        'daily_payments',
        ['sale_message_id']
    )


def downgrade() -> None:
    op.drop_index('idx_daily_payments_sale_message_id', table_name='daily_payments')
