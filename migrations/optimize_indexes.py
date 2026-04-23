"""Дополнительные индексы для оптимизации производительности."""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # GIN индекс для полнотекстового поиска по товарам
    op.create_index(
        'idx_items_text_gin',
        'items',
        ['text'],
        postgresql_using='gin',
        postgresql_ops={'text': 'gin_trgm_ops'}
    )
    # GIN индекс для поиска по payment_details
    op.create_index(
        'idx_purchases_payment_details_gin',
        'purchases',
        ['payment_details'],
        postgresql_using='gin'
    )
    # Составной индекс для быстрого получения остатков
    op.create_index(
        'idx_items_category_booked',
        'items',
        ['category_id', 'is_booked']
    )


def downgrade():
    op.drop_index('idx_items_text_gin', table_name='items')
    op.drop_index('idx_purchases_payment_details_gin', table_name='purchases')
    op.drop_index('idx_items_category_booked', table_name='items')
