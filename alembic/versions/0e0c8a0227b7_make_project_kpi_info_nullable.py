"""make project kpi_info nullable

Revision ID: 0e0c8a0227b7
Revises: bcf6f0b3a04e
Create Date: 2025-11-10 16:49:39.431942

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e0c8a0227b7'
down_revision: Union[str, None] = 'bcf6f0b3a04e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'project',
        'kpi_info',
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'project',
        'kpi_info',
        existing_type=sa.String(),
        nullable=False,
    )
