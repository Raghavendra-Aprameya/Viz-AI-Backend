"""add autopilot fields to dashboard

Revision ID: a1b2c3d4e5f6
Revises: e4f9a1b2c3d4
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'e4f9a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'dashboard',
        sa.Column('is_autopilot', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column(
        'dashboard',
        sa.Column('kpi_goals', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('dashboard', 'kpi_goals')
    op.drop_column('dashboard', 'is_autopilot')
