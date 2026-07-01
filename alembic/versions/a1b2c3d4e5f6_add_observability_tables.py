"""Add observability tables: llm_trace, daily_usage_rollup, llm_pricing

Revision ID: a1b2c3d4e5f6
Revises: be169106faaa
Create Date: 2026-06-05 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "be169106faaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE llm_trace_status AS ENUM ('success','error','timeout','cancelled');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai_service_type AS ENUM (
                'probe_mode','ai_assistant','text_enhancement',
                'ontology_refinement','insights_generation','query_generation','other'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── llm_pricing ──────────────────────────────────────────────────────────
    op.create_table(
        "llm_pricing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("prompt_cost_per_1k", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("completion_cost_per_1k", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Seed standard OpenAI & Google pricing (Jun 2026 rates — update as needed)
    op.execute("""
        INSERT INTO llm_pricing (id, provider, model_name, prompt_cost_per_1k, completion_cost_per_1k, effective_from)
        VALUES
          (gen_random_uuid(), 'openai',  'gpt-4o',           0.00500, 0.01500, '2024-01-01'),
          (gen_random_uuid(), 'openai',  'gpt-5.4-mini',      0.00015, 0.00060, '2024-07-01'),
          (gen_random_uuid(), 'openai',  'gpt-4.1-mini',     0.00040, 0.00160, '2025-04-14'),
          (gen_random_uuid(), 'openai',  'gpt-4.1',          0.00200, 0.00800, '2025-04-14'),
          (gen_random_uuid(), 'google',  'gemini-2.5-flash', 0.00015, 0.00035, '2025-05-01'),
          (gen_random_uuid(), 'google',  'gemini-pro',       0.00025, 0.00050, '2024-01-01'),
          (gen_random_uuid(), 'google',  'gemini-2.0-flash', 0.00010, 0.00040, '2025-02-01')
        ON CONFLICT DO NOTHING;
    """)

    # ── llm_trace ────────────────────────────────────────────────────────────
    op.create_table(
        "llm_trace",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.String(256), nullable=True),
        sa.Column("chart_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_service", sa.Enum("probe_mode","ai_assistant","text_enhancement","ontology_refinement","insights_generation","query_generation","other", name="ai_service_type", create_type=False), nullable=False, server_default="probe_mode"),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=True, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=True, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 8), nullable=True, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("prompt_text", sa.Text, nullable=True),
        sa.Column("completion_text", sa.Text, nullable=True),
        sa.Column("sql_generated", sa.Text, nullable=True),
        sa.Column("sql_retries", sa.Integer, nullable=True, server_default="0"),
        sa.Column("schema_tables_used", postgresql.JSONB, nullable=True),
        sa.Column("agent_steps", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.Enum("success","error","timeout","cancelled", name="llm_trace_status", create_type=False), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_llm_trace_session_id", "llm_trace", ["session_id"])
    op.create_index("ix_llm_trace_project_id", "llm_trace", ["project_id"])
    op.create_index("ix_llm_trace_user_id", "llm_trace", ["user_id"])
    op.create_index("ix_llm_trace_created_at", "llm_trace", ["created_at"])
    op.create_index("ix_llm_trace_ai_service", "llm_trace", ["ai_service"])

    # ── daily_usage_rollup ───────────────────────────────────────────────────
    op.create_table(
        "daily_usage_rollup",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rollup_date", sa.Date, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_service", sa.Enum("probe_mode","ai_assistant","text_enhancement","ontology_refinement","insights_generation","query_generation","other", name="ai_service_type", create_type=False), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("total_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_prompt_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_completion_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Numeric(14, 8), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Integer, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_daily_usage_rollup_date", "daily_usage_rollup", ["rollup_date"])
    op.create_index("ix_daily_usage_rollup_project_id", "daily_usage_rollup", ["project_id"])


def downgrade() -> None:
    op.drop_table("daily_usage_rollup")
    op.drop_index("ix_llm_trace_ai_service", "llm_trace")
    op.drop_index("ix_llm_trace_created_at", "llm_trace")
    op.drop_index("ix_llm_trace_user_id", "llm_trace")
    op.drop_index("ix_llm_trace_project_id", "llm_trace")
    op.drop_index("ix_llm_trace_session_id", "llm_trace")
    op.drop_table("llm_trace")
    op.drop_table("llm_pricing")
    op.execute("DROP TYPE IF EXISTS ai_service_type;")
    op.execute("DROP TYPE IF EXISTS llm_trace_status;")
