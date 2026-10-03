"""
Weather history + real weather fetch via Open-Meteo.

Two functions:
  fetch_current_weather()  — current conditions + next-6h rain forecast
  fetch_weather_history()  — 30-day daily summary, INCLUDING the official
                              FAO-56 Penman-Monteith reference ET₀

The ET₀ comes from Open-Meteo's historical-forecast API, which computes
it server-side using the same Penman-Monteith method used by agronomists
worldwide. This avoids the Hargreaves overestimation problem in humid
tropical climates.

Coordinates: uses the plot's lat/long if set; otherwise falls back to
Mailapitiya, Kandy (7.2217°N, 80.7446°E).
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core.safety.context import WeatherSnapshot


log = logging.getLogger(__name__)


# --- Configuration ----------------------------------------------------------

DEFAULT_LAT = 7.2217
DEFAULT_LON = 80.7446

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# Historical forecast API — has past data with full daily fields,
# including FAO-56 ET₀. (Not the same as archive-api, which lacks ET₀.)
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

TIMEZONE = "Asia/Colombo"
HTTP_TIMEOUT = 15.0


# --- Current weather --------------------------------------------------------

def fetch_current_weather(
    latitude: float | None,
    longitude: float | None,
) -> WeatherSnapshot:
    """
    Fetch current conditions + next-6h rain forecast.
    Falls back to conservative defaults on any error.
    """
    lat = latitude if latitude is not None else DEFAULT_LAT
    lon = longitude if longitude is not None else DEFAULT_LON

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
        "hourly": "precipitation",
        "forecast_days": 1,
        "timezone": TIMEZONE,
        "wind_speed_unit": "kmh",
    }

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.get(FORECAST_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning(f"Open-Meteo forecast call failed: {e}")
        return _fallback_weather()

    try:
        current = data["current"]
        rain_6h = _sum_next_6h_rain(data.get("hourly", {}), current["time"])

        return WeatherSnapshot(
            temp_c=float(current["temperature_2m"]),
            humidity=float(current["relative_humidity_2m"]) / 100.0,
            wind_kmh=float(current["wind_speed_10m"]),
            rain_forecast_mm_6h=rain_6h,
            fetched_at=datetime.now(timezone.utc),
            source="open-meteo",
        )
    except (KeyError, TypeError, ValueError) as e:
        log.warning(f"Open-Meteo response malformed: {e}")
        return _fallback_weather()


def _sum_next_6h_rain(hourly: dict, current_iso_time: str) -> float:
    """Sum precipitation over the next 6 hours from hourly data."""
    times = hourly.get("time") or []
    precip = hourly.get("precipitation") or []
    if not times or not precip:
        return 0.0

    try:
        current_hour = current_iso_time[:13] + ":00"
    except Exception:
        return 0.0

    try:
        idx = times.index(current_hour)
    except ValueError:
        return 0.0

    window = precip[idx: idx + 6]
    return round(sum(v for v in window if v is not None), 2)


def _fallback_weather() -> WeatherSnapshot:
    """Conservative fallback if the API is unreachable."""
    return WeatherSnapshot(
        temp_c=25.0,
        humidity=0.75,
        wind_kmh=5.0,
        rain_forecast_mm_6h=0.0,
        fetched_at=datetime.now(timezone.utc),
        source="fallback",
    )


# --- Weather history --------------------------------------------------------

@dataclass(frozen=True)
class DailyWeather:
    day: str              # 'YYYY-MM-DD'
    temp_max_c: float
    temp_min_c: float
    rain_mm: float
    wind_max_kmh: float
    et0_mm: float         # FAO-56 reference ET₀, from Open-Meteo


@dataclass(frozen=True)
class WeatherHistorySummary:
    window_days: int
    total_rain_mm: float
    total_et0_mm: float
    avg_temp_max_c: float
    avg_temp_min_c: float
    max_wind_kmh: float
    daily: list[DailyWeather]
    pattern: str          # 'dry' | 'normal' | 'wet'


def fetch_weather_history(
    latitude: float | None,
    longitude: float | None,
    days: int = 30,
) -> WeatherHistorySummary | None:
    """
    Fetch daily weather summary for the last `days`.
    Uses the historical-forecast API, which includes ET₀.
    Returns None on error.
    """
    lat = latitude if latitude is not None else DEFAULT_LAT
    lon = longitude if longitude is not None else DEFAULT_LON

    # Historical forecast has data up to ~2 days ago; use that as end.
    end_date = (datetime.now(timezone.utc) - timedelta(days=2)).date()
    start_date = end_date - timedelta(days=days - 1)

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": (
            "temperature_2m_max,temperature_2m_min,"
            "precipitation_sum,wind_speed_10m_max,"
            "et0_fao_evapotranspiration"
        ),
        "timezone": TIMEZONE,
        "wind_speed_unit": "kmh",
    }

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.get(HISTORICAL_FORECAST_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning(f"Open-Meteo historical forecast call failed: {e}")
        return None

    try:
        d = data["daily"]
        times = d["time"]
        tmax = d["temperature_2m_max"]
        tmin = d["temperature_2m_min"]
        rain = d["precipitation_sum"]
        wind = d["wind_speed_10m_max"]
        et0 = d.get("et0_fao_evapotranspiration", [None] * len(times))
    except (KeyError, TypeError) as e:
        log.warning(f"Open-Meteo historical response malformed: {e}")
        return None

    if not times:
        return None

    daily = []
    for i, day in enumerate(times):
        if tmax[i] is None or tmin[i] is None:
            continue
        daily.append(DailyWeather(
            day=day,
            temp_max_c=float(tmax[i]),
            temp_min_c=float(tmin[i]),
            rain_mm=float(rain[i] or 0.0),
            wind_max_kmh=float(wind[i] or 0.0),
            et0_mm=float(et0[i] or 0.0),
        ))

    if not daily:
        return None

    total_rain = sum(d.rain_mm for d in daily)
    total_et0 = sum(d.et0_mm for d in daily)
    avg_tmax = sum(d.temp_max_c for d in daily) / len(daily)
    avg_tmin = sum(d.temp_min_c for d in daily) / len(daily)
    max_wind = max(d.wind_max_kmh for d in daily)

    # Pattern classification for Kandy region (typical ~150-200mm/month)
    if total_rain < 100:
        pattern = "dry"
    elif total_rain > 250:
        pattern = "wet"
    else:
        pattern = "normal"

    return WeatherHistorySummary(
        window_days=len(daily),
        total_rain_mm=round(total_rain, 1),
        total_et0_mm=round(total_et0, 1),
        avg_temp_max_c=round(avg_tmax, 1),
        avg_temp_min_c=round(avg_tmin, 1),
        max_wind_kmh=round(max_wind, 1),
        daily=daily,
        pattern=pattern,
    )


def format_weather_history_for_prompt(hist: WeatherHistorySummary | None) -> str:
    """Render the weather history for the agent prompt."""
    if hist is None:
        return ""

    lines = [
        f"WEATHER HISTORY — LAST {hist.window_days} DAYS (Mailapitiya, Kandy):",
        f"  Total rainfall: {hist.total_rain_mm:.1f} mm",
        f"  Total reference ET₀: {hist.total_et0_mm:.1f} mm",
        f"  Avg temp: {hist.avg_temp_min_c:.1f}°C - {hist.avg_temp_max_c:.1f}°C",
        f"  Max wind: {hist.max_wind_kmh:.1f} km/h",
        f"  Pattern: {hist.pattern.upper()}",
    ]

    lines.append("  Recent days:")
    for d in hist.daily[-5:]:
        lines.append(
            f"    {d.day}: {d.temp_min_c:.1f}-{d.temp_max_c:.1f}°C, "
            f"{d.rain_mm:.1f}mm rain, ET₀ {d.et0_mm:.2f}mm, "
            f"wind max {d.wind_max_kmh:.0f}km/h"
        )

    return "\n".join(lines)