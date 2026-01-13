"""add home insights table

Revision ID: c1d2e3f4a5b6
Revises: cd06cabc976c
Create Date: 2026-01-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'cd06cabc976c'
branch_labels = None
depends_on = None


def upgrade():
    # Create home_insights table
    op.create_table(
        'home_insights',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('insight_type', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('impact', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_home_insights_user_id'), 'home_insights', ['user_id'], unique=False)
    op.create_index(op.f('ix_home_insights_project_id'), 'home_insights', ['project_id'], unique=False)


def downgrade():
    # Drop home_insights table
    op.drop_index(op.f('ix_home_insights_project_id'), table_name='home_insights')
    op.drop_index(op.f('ix_home_insights_user_id'), table_name='home_insights')
    op.drop_table('home_insights')

