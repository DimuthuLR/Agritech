"""
Agronomic calculations — water balance and GDD.

ET₀ now comes from Open-Meteo's historical-forecast API (FAO-56
Penman-Monteith, computed server-side). We no longer compute Hargreaves
locally — that formula overestimates by 2-3x in humid tropical climates.

What we still compute:
  - Daily net water balance (rain - ET₀)
  - Accumulated GDD (growing degree days) above crop base temperature
  - 30-day summary statistics
"""
from dataclasses import dataclass
from datetime import date

from app.services.weather_history import DailyWeather


# ---------------------------------------------------------------------------
# Crop-specific base temperatures for GDD (°C)
# ---------------------------------------------------------------------------

CROP_BASE_TEMPS_C = {
    "tomato": 10.0,
    "chili": 10.0,
    "bell_pepper": 10.0,
    "cucumber": 10.0,
    "brinjal": 10.0,
    "lettuce": 4.0,
    "cabbage": 4.0,
    "carrot": 5.0,
}

DEFAULT_BASE_TEMP_C = 10.0


def _daily_gdd(tmax_c: float, tmin_c: float, base_c: float) -> float:
    """Single-day GDD above base temperature."""
    tmean = (tmax_c + tmin_c) / 2
    return max(0.0, tmean - base_c)


# ---------------------------------------------------------------------------
# Summary dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyAgronomy:
    day: str
    et0_mm: float
    gdd: float
    rain_mm: float
    net_balance_mm: float   # rain - et0


@dataclass(frozen=True)
class AgronomicSummary:
    window_days: int
    total_et0_mm: float
    total_rain_mm: float
    net_balance_mm: float
    avg_et0_mm_per_day: float
    total_gdd: float
    base_temp_c: float
    daily: list[DailyAgronomy]


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def compute_agronomic_summary(
    daily_weather: list[DailyWeather],
    latitude_deg: float,
    crop: str,
) -> AgronomicSummary | None:
    """
    Compute water balance and GDD from daily weather.
    ET₀ is taken from the Open-Meteo-provided field on each DailyWeather.
    """
    if not daily_weather:
        return None

    base_temp = CROP_BASE_TEMPS_C.get(crop.lower(), DEFAULT_BASE_TEMP_C)

    daily_out: list[DailyAgronomy] = []
    total_et0 = 0.0
    total_gdd = 0.0
    total_rain = 0.0

    for d in daily_weather:
        et0 = d.et0_mm
        gdd = _daily_gdd(d.temp_max_c, d.temp_min_c, base_temp)
        net = d.rain_mm - et0

        daily_out.append(DailyAgronomy(
            day=d.day,
            et0_mm=round(et0, 2),
            gdd=round(gdd, 1),
            rain_mm=round(d.rain_mm, 1),
            net_balance_mm=round(net, 2),
        ))
        total_et0 += et0
        total_gdd += gdd
        total_rain += d.rain_mm

    if not daily_out:
        return None

    return AgronomicSummary(
        window_days=len(daily_out),
        total_et0_mm=round(total_et0, 1),
        total_rain_mm=round(total_rain, 1),
        net_balance_mm=round(total_rain - total_et0, 1),
        avg_et0_mm_per_day=round(total_et0 / len(daily_out), 2),
        total_gdd=round(total_gdd, 1),
        base_temp_c=base_temp,
        daily=daily_out,
    )


# ---------------------------------------------------------------------------
# Format for prompt
# ---------------------------------------------------------------------------

def format_agronomy_for_prompt(summary: AgronomicSummary | None) -> str:
    """Render agronomic calculations as text for the agent prompt."""
    if summary is None:
        return ""

    balance = summary.net_balance_mm
    if balance < -20:
        note = "significant water deficit"
    elif balance < 0:
        note = "mild deficit"
    elif balance < 20:
        note = "balanced"
    else:
        note = "water surplus"

    lines = [
        f"AGRONOMIC CONTEXT — LAST {summary.window_days} DAYS:",
        f"  Reference ET₀ total: {summary.total_et0_mm:.1f} mm",
        f"  Rainfall total: {summary.total_rain_mm:.1f} mm",
        f"  Water balance: {balance:+.1f} mm ({note})",
        f"  Avg daily ET₀: {summary.avg_et0_mm_per_day:.2f} mm/day",
        f"  Accumulated GDD (base {summary.base_temp_c:.0f}°C): {summary.total_gdd:.0f}",
        "  Last 5 days (ET₀ / rain / net balance):",
    ]

    for d in summary.daily[-5:]:
        lines.append(
            f"    {d.day}: ET₀ {d.et0_mm:.2f}mm, rain {d.rain_mm:.1f}mm, "
            f"net {d.net_balance_mm:+.2f}mm"
        )

    return "\n".join(lines)