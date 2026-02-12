"""merge heads for chart status

Revision ID: bcf6f0b3a04e
Revises: a4490db0d396, b3d4c2e8f1a2
Create Date: 2025-11-10 11:35:52.534808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcf6f0b3a04e'
down_revision: Union[str, None] = ('a4490db0d396', 'b3d4c2e8f1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
