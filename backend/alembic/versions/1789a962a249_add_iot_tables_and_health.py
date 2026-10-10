"""add_iot_tables_and_health

Revision ID: 1789a962a249
Revises: 630bd5eadc0c
Create Date: 2026-10-10 21:37:58.279401

Adds:
  - device_claim_codes table (pre-registration codes)
  - health columns on devices (uptime, heap, RSSI, battery, errors)
  - claimed_at on devices
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers (kept from Alembic)
revision: str = "R1789a962a249"
down_revision: Union[str, None] = "630bd5eadc0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Claim codes ---------------------------------------------------
    op.create_table(
        "device_claim_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "used_by_device_id",
            UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_device_claim_codes_tenant_id",
        "device_claim_codes", ["tenant_id"],
    )
    op.create_index(
        "ix_device_claim_codes_expires_at",
        "device_claim_codes", ["expires_at"],
    )

    # ---- Device health columns ----------------------------------------
    op.add_column("devices", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("hw_version", sa.String(64), nullable=True))
    op.add_column("devices", sa.Column("chip_type", sa.String(32), nullable=True))
    op.add_column("devices", sa.Column("uptime_sec", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("free_heap_kb", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("rssi_dbm", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("battery_v", sa.Numeric(5, 2), nullable=True))
    op.add_column("devices", sa.Column("last_error_code", sa.String(64), nullable=True))
    op.add_column("devices", sa.Column("last_error_message", sa.Text(), nullable=True))
    op.add_column("devices", sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in (
        "last_error_at", "last_error_message", "last_error_code",
        "battery_v", "rssi_dbm", "free_heap_kb", "uptime_sec",
        "chip_type", "hw_version", "claimed_at",
    ):
        op.drop_column("devices", col)

    op.drop_index("ix_device_claim_codes_expires_at", "device_claim_codes")
    op.drop_index("ix_device_claim_codes_tenant_id", "device_claim_codes")
    op.drop_table("device_claim_codes")