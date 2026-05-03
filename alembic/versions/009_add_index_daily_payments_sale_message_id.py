"""Add index on daily_payments.sale_message_id

Revision ID: 009
Revises: 008
Create Date: 2026-04-11 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонку sale_message_id, если её ещё нет
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('daily_payments')]
    if 'sale_message_id' not in columns:
        op.add_column('daily_payments', sa.Column('sale_message_id', sa.BigInteger(), nullable=True))

    # Создаём индекс
    op.create_index(
        'idx_daily_payments_sale_message_id',
        'daily_payments',
        ['sale_message_id']
    )


def downgrade() -> None:
    op.drop_index('idx_daily_payments_sale_message_id', table_name='daily_payments')
    # Колонку sale_message_id не удаляем, так как она могла существовать ранее
