"""Added connection_name in Database ConnectionModel

Revision ID: 2a414a52ffc1
Revises: ef3b7af218f7
Create Date: 2025-04-04 14:46:44.773177

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a414a52ffc1'
down_revision: Union[str, None] = 'ef3b7af218f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('database_connection', sa.Column('connection_name', sa.String(), nullable=False))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('database_connection', 'connection_name')
    # ### end Alembic commands ###
