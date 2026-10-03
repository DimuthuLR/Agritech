"""
Trend summaries — aggregate historical data for agent reasoning.

The current SafetyContext is a *snapshot*. This module provides the
*trend* layer: aggregated data over time so the agent can reason about
direction and rate of change, not just current values.

Read-only against the continuous aggregate sensor_1h. Fast at any scale.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyBucket:
    day: str              # 'YYYY-MM-DD'
    avg_value: float
    min_value: float
    max_value: float
    sample_count: int


@dataclass(frozen=True)
class TrendSummary:
    metric: str
    window_days: int
    overall_avg: float
    overall_min: float
    overall_max: float
    total_samples: int
    daily: list[DailyBucket]
    direction: str        # 'rising' | 'falling' | 'stable' | 'insufficient_data'
    change_percent: float # first day → last day


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_soil_moisture_trend(
    db: Session,
    plot_id: UUID,
    days: int = 7,
) -> TrendSummary | None:
    """
    Aggregate soil_moisture over the last `days` from sensor_1h.
    Returns None if no data is available.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    sql = text("""
        SELECT
            date_trunc('day', bucket) AS day,
            AVG(avg_value) AS day_avg,
            MIN(min_value) AS day_min,
            MAX(max_value) AS day_max,
            SUM(sample_count)::int AS day_count
        FROM sensor_1h
        WHERE plot_id = :plot_id
          AND metric = 'soil_moisture'
          AND bucket >= :since
        GROUP BY day
        ORDER BY day ASC
    """)

    rows = (
        db.execute(sql, {"plot_id": str(plot_id), "since": since})
        .mappings()
        .all()
    )
    if not rows:
        return None

    daily = [
        DailyBucket(
            day=r["day"].strftime("%Y-%m-%d"),
            avg_value=float(r["day_avg"]),
            min_value=float(r["day_min"]),
            max_value=float(r["day_max"]),
            sample_count=int(r["day_count"]),
        )
        for r in rows
    ]

    all_avgs = [d.avg_value for d in daily]
    overall_avg = sum(all_avgs) / len(all_avgs)
    overall_min = min(d.min_value for d in daily)
    overall_max = max(d.max_value for d in daily)
    total_samples = sum(d.sample_count for d in daily)

    direction, change_percent = _compute_direction(daily)

    return TrendSummary(
        metric="soil_moisture",
        window_days=days,
        overall_avg=overall_avg,
        overall_min=overall_min,
        overall_max=overall_max,
        total_samples=total_samples,
        daily=daily,
        direction=direction,
        change_percent=change_percent,
    )


def _compute_direction(daily: list[DailyBucket]) -> tuple[str, float]:
    """
    Compare first day's average to last day's average.
    Returns (direction, change_percent).
    """
    if len(daily) < 2:
        return ("insufficient_data", 0.0)

    first = daily[0].avg_value
    last = daily[-1].avg_value

    if first == 0:
        return ("stable", 0.0)

    change = (last - first) / first * 100.0

    if abs(change) < 5.0:
        return ("stable", change)
    if change > 0:
        return ("rising", change)
    return ("falling", change)


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------

def format_trend_for_prompt(trend: TrendSummary | None) -> str:
    """
    Render a TrendSummary as text for the LLM prompt.
    Returns empty string if trend is None.
    """
    if trend is None:
        return ""

    lines = [
        f"SOIL MOISTURE TREND — LAST {trend.window_days} DAYS:",
        (
            f"  Overall: avg {trend.overall_avg:.3f}, "
            f"min {trend.overall_min:.3f}, max {trend.overall_max:.3f} "
            f"({trend.total_samples} hourly samples)"
        ),
        "  Daily averages:",
    ]

    for d in trend.daily:
        lines.append(
            f"    {d.day}: avg {d.avg_value:.3f} "
            f"(min {d.min_value:.3f}, max {d.max_value:.3f}, "
            f"{d.sample_count} samples)"
        )

    if trend.direction == "insufficient_data":
        lines.append("  Trend: insufficient data (need at least 2 days)")
    else:
        lines.append(
            f"  Trend: {trend.direction.upper()} "
            f"({trend.change_percent:+.1f}% from first to last day)"
        )

    return "\n".join(lines)