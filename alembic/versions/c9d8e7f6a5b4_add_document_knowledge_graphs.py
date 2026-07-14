"""
Add document_knowledge_graphs table for PDF knowledge graphs.

Revision ID: c9d8e7f6a5b4
Revises: 7bf21dbfb77b, b2c3d4e5f6a7
Create Date: 2026-07-13 13:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = ("7bf21dbfb77b", "b2c3d4e5f6a7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_knowledge_graphs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("graph_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_knowledge_graphs_user_id",
        "document_knowledge_graphs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_knowledge_graphs_user_id", table_name="document_knowledge_graphs")
    op.drop_table("document_knowledge_graphs")
