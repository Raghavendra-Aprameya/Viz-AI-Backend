"""add_document_knowledge_graphs

Revision ID: c9d8e7f6a5b4
Revises: 7bf21dbfb77b
Create Date: 2026-07-15 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = ("7bf21dbfb77b", "b2c3d4e5f6a7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_knowledge_graphs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False, server_default=""),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("graph_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_document_knowledge_graphs_user_id",
        "document_knowledge_graphs",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_knowledge_graphs_user_id", table_name="document_knowledge_graphs")
    op.drop_table("document_knowledge_graphs")
