"""add database_connection_scope table for multi-catalog support

Revision ID: 6a9d3e2b1f4c
Revises: 3f1b2d9a7c44, c1d2e3f4a5b6
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6a9d3e2b1f4c'
down_revision: Union[str, Sequence[str], None] = ('3f1b2d9a7c44', 'c1d2e3f4a5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'database_connection_scope',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('catalog_name', sa.String(), nullable=False),
        sa.Column('schema_name', sa.String(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['connection_id'], ['database_connection.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_database_connection_scope_connection_id',
        'database_connection_scope',
        ['connection_id'],
        unique=False,
    )
    op.create_unique_constraint(
        'uq_database_connection_scope_connection_catalog_schema',
        'database_connection_scope',
        ['connection_id', 'catalog_name', 'schema_name'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_database_connection_scope_connection_catalog_schema', 'database_connection_scope', type_='unique')
    op.drop_index('ix_database_connection_scope_connection_id', table_name='database_connection_scope')
    op.drop_table('database_connection_scope')
