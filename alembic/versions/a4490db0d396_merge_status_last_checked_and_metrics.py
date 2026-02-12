"""merge_status_last_checked_and_metrics

Revision ID: a4490db0d396
Revises: f8c9a3b4e2d1, 133d365815ab
Create Date: 2025-11-05 16:10:38.134762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4490db0d396'
down_revision: Union[str, None] = ('f8c9a3b4e2d1', '133d365815ab')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
