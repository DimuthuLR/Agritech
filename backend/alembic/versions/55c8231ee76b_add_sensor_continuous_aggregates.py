"""add sensor continuous aggregates

Revision ID: 55c8231ee76b
Revises: e1b6b5a7733a
Create Date: 2026-10-02

Creates two continuous aggregates over sensor_readings:
  sensor_1h — 1-hour rollups
  sensor_6h — 6-hour rollups (built directly from raw readings for
              compatibility across TimescaleDB versions)

Refresh policies are set so TimescaleDB keeps them current automatically.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '55c8231ee76b'
down_revision: Union[str, None] = 'e1b6b5a7733a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- sensor_1h: hourly rollup of raw readings ---
    op.execute("""
        CREATE MATERIALIZED VIEW sensor_1h
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', time) AS bucket,
            tenant_id,
            plot_id,
            device_id,
            metric,
            avg(value)  AS avg_value,
            min(value)  AS min_value,
            max(value)  AS max_value,
            count(*)    AS sample_count
        FROM sensor_readings
        GROUP BY bucket, tenant_id, plot_id, device_id, metric
        WITH NO DATA;
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy('sensor_1h',
            start_offset     => INTERVAL '30 days',
            end_offset       => INTERVAL '1 hour',
            schedule_interval => INTERVAL '30 minutes');
    """)

    # --- sensor_6h: 6-hour rollup, built directly from raw readings ---
    op.execute("""
        CREATE MATERIALIZED VIEW sensor_6h
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('6 hours', time) AS bucket,
            tenant_id,
            plot_id,
            device_id,
            metric,
            avg(value)  AS avg_value,
            min(value)  AS min_value,
            max(value)  AS max_value,
            count(*)    AS sample_count
        FROM sensor_readings
        GROUP BY bucket, tenant_id, plot_id, device_id, metric
        WITH NO DATA;
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy('sensor_6h',
            start_offset     => INTERVAL '90 days',
            end_offset       => INTERVAL '6 hours',
            schedule_interval => INTERVAL '1 hour');
    """)


def downgrade() -> None:
    op.execute("SELECT remove_continuous_aggregate_policy('sensor_6h', if_exists => TRUE);")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS sensor_6h CASCADE;")

    op.execute("SELECT remove_continuous_aggregate_policy('sensor_1h', if_exists => TRUE);")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS sensor_1h CASCADE;")