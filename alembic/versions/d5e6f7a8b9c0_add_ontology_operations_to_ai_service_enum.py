"""add ontology operations to ai_service_type enum

Revision ID: d5e6f7a8b9c0
Revises: c9d8e7f6a5b4
Create Date: 2026-07-27 13:50:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c9d8e7f6a5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_service_type ADD VALUE IF NOT EXISTS 'ontology_sync_table';")
    op.execute("ALTER TYPE ai_service_type ADD VALUE IF NOT EXISTS 'ontology_generate_table_description';")
    op.execute("ALTER TYPE ai_service_type ADD VALUE IF NOT EXISTS 'ontology_generate_column_description';")


def downgrade() -> None:
    # Note: PostgreSQL does not support removing values from an ENUM type without recreating the type.
    pass
