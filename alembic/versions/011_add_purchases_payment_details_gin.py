"""Add GIN index on purchases.payment_details

Revision ID: 011
Revises: 010
Create Date: 2026-04-22 12:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'idx_purchases_payment_details_gin',
        'purchases',
        ['payment_details'],
        postgresql_using='gin'
    )


def downgrade() -> None:
    op.drop_index('idx_purchases_payment_details_gin', table_name='purchases')
