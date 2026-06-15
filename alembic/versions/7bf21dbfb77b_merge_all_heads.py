"""merge_all_heads

Revision ID: 7bf21dbfb77b
Revises: 3f1b2d9a7c44, a1b2c3d4e5f6, e4f9a1b2c3d4
Create Date: 2026-06-05 17:52:07.895123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7bf21dbfb77b'
down_revision: Union[str, None] = ('3f1b2d9a7c44', 'a1b2c3d4e5f6', 'e4f9a1b2c3d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
