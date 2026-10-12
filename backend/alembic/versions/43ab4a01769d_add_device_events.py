"""add_device_events

Revision ID: 43ab4a01769d
Revises: R1789a962a249
Create Date: 2026-10-11 10:50:27.514076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '43ab4a01769d'
down_revision: Union[str, None] = 'R1789a962a249'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("cmd_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_device_events_device_occurred",
        "device_events", ["device_id", "occurred_at"],
    )
    op.create_index(
        "ix_device_events_tenant_occurred",
        "device_events", ["tenant_id", "occurred_at"],
    )
    op.create_index(
        "ix_device_events_cmd_id",
        "device_events", ["cmd_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_device_events_cmd_id", "device_events")
    op.drop_index("ix_device_events_tenant_occurred", "device_events")
    op.drop_index("ix_device_events_device_occurred", "device_events")
    op.drop_table("device_events")