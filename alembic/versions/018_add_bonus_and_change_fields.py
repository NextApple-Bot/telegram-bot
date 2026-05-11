"""add bonus and change fields to items

Revision ID: 018
Revises: 017
Create Date: 2026-05-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('items', sa.Column('sale_bonus', sa.Float(), nullable=True))
    op.add_column('items', sa.Column('sale_change', sa.Float(), nullable=True))
    op.add_column('items', sa.Column('sale_change_type', sa.String(), nullable=True))
    op.add_column('items', sa.Column('booking_bonus', sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_column('items', 'booking_bonus')
    op.drop_column('items', 'sale_change_type')
    op.drop_column('items', 'sale_change')
    op.drop_column('items', 'sale_bonus')
