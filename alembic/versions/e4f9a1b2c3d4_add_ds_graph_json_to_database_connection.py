"""add ds_graph_json to database_connection

Revision ID: e4f9a1b2c3d4
Revises: c1d2e3f4a5b6
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e4f9a1b2c3d4'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('database_connection', sa.Column('ds_graph_json', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('database_connection', 'ds_graph_json')
