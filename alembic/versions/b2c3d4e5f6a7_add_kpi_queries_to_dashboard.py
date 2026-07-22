"""add kpi_queries to dashboard

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'dashboard',
        sa.Column('kpi_queries', JSONB, nullable=True)
    )


def downgrade() -> None:
    op.drop_column('dashboard', 'kpi_queries')
