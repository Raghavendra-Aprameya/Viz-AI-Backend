"""Cascade delete for user_project_role.project_id FK

Revision ID: 3f1b2d9a7c44
Revises: cd06cabc976c
Create Date: 2026-04-28

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3f1b2d9a7c44"
down_revision: Union[str, None] = "cd06cabc976c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "user_project_role_project_id_fkey",
        "user_project_role",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "user_project_role_project_id_fkey",
        "user_project_role",
        "project",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "user_project_role_project_id_fkey",
        "user_project_role",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "user_project_role_project_id_fkey",
        "user_project_role",
        "project",
        ["project_id"],
        ["id"],
    )
