"""add support_sessions and chat_sessions tables

Revision ID: (keep what Alembic generated)
Revises: (keep what Alembic generated)
Create Date: (keep what Alembic generated)

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# IMPORTANT: keep the revision and down_revision lines that Alembic
# generated at the top of this file. The values below are placeholders.
# Only replace the upgrade() and downgrade() bodies.
revision: str = "630bd5eadc0c"
down_revision: Union[str, None] = "b0609b8f9ec1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- support_sessions -----------------------------------------------
    op.create_table(
        "support_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "platform_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ticket_reference", sa.String(128), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
    )
    op.create_index(
        "ix_support_sessions_platform_user",
        "support_sessions", ["platform_user_id"],
    )
    op.create_index(
        "ix_support_sessions_target_user",
        "support_sessions", ["target_user_id"],
    )
    op.create_index(
        "ix_support_sessions_target_tenant",
        "support_sessions", ["target_tenant_id"],
    )
    op.create_index(
        "ix_support_sessions_started_at",
        "support_sessions", ["started_at"],
    )

    # --- chat_sessions --------------------------------------------------
    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plot_id",
            UUID(as_uuid=True),
            sa.ForeignKey("plots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column(
            "messages",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_chat_sessions_tenant_id", "chat_sessions", ["tenant_id"],
    )
    op.create_index(
        "ix_chat_sessions_user_id", "chat_sessions", ["user_id"],
    )
    op.create_index(
        "ix_chat_sessions_plot_id", "chat_sessions", ["plot_id"],
    )
    op.create_index(
        "ix_chat_sessions_last_message_at", "chat_sessions", ["last_message_at"],
    )
    op.create_index(
        "ix_chat_sessions_tenant_last_msg",
        "chat_sessions", ["tenant_id", "last_message_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_tenant_last_msg", "chat_sessions")
    op.drop_index("ix_chat_sessions_last_message_at", "chat_sessions")
    op.drop_index("ix_chat_sessions_plot_id", "chat_sessions")
    op.drop_index("ix_chat_sessions_user_id", "chat_sessions")
    op.drop_index("ix_chat_sessions_tenant_id", "chat_sessions")
    op.drop_table("chat_sessions")

    op.drop_index("ix_support_sessions_started_at", "support_sessions")
    op.drop_index("ix_support_sessions_target_tenant", "support_sessions")
    op.drop_index("ix_support_sessions_target_user", "support_sessions")
    op.drop_index("ix_support_sessions_platform_user", "support_sessions")
    op.drop_table("support_sessions")