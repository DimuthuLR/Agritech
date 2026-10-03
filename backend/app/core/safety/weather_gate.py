"""
Weather gate — the second checkpoint in the safety pipeline.

Suppresses actuator actions based on current weather and near-term forecast.
This runs BEFORE limit validation. Rationale:

  - Even a fully compliant 30-minute irrigation is wasteful if it rains
    in the next hour.
  - Spraying in wind = drift damage to neighbours' crops. Legal liability.
  - Spraying in heat = phytotoxicity (leaf burn). Yield loss.

Returns a reason string if suppressed, or None if allowed. The reason
becomes the audit log entry — always explain WHY something was blocked.

Sri Lanka context:
  - Two monsoon systems (Southwest May-Sep, Northeast Oct-Jan) drive
    most rainfall. Rain forecasts are more reliable than in continental
    climates — the monsoon is predictable within hours.
  - Wind thresholds reflect the island's coastal exposure. Highland tea
    estates rarely see high winds; dry-zone coastal plots do.
  - Temperature rarely blocks agricultural work in Sri Lanka (tropical
    climate), but hill-country (Nuwara Eliya, ~1900m) can drop low enough
    that cold-water irrigation shocks plants. Deferred.
"""
from app.core.safety.context import SafetyContext


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
#
# These are the "if X, then suppress" points. Conservative by design —
# if we're wrong, we under-irrigate (yield loss) rather than over-irrigate
# (root rot, wasted water, chemical runoff).

# Rain — if forecast exceeds this in the next 6 hours, don't irrigate.
# 5mm is roughly "the ground will get wet."
RAIN_SUPPRESS_IRRIGATION_MM = 5.0

# Rain — if forecast exceeds this in the next 6 hours, don't spray chemicals.
# Chemicals need to stay on the leaf surface for 4-6 hours to be absorbed.
# 2mm washes them off.
RAIN_SUPPRESS_SPRAY_MM = 2.0

# Wind — spraying above this speed causes drift. Drift = wasted chemical +
# damage to neighbours + regulatory violation.
WIND_SUPPRESS_SPRAY_KMH = 15.0

# Wind — above this, irrigation sprayers (impact sprinklers) are inaccurate.
# Drip is unaffected but we can't know the irrigation method here, so be conservative.
WIND_SUPPRESS_IRRIGATION_KMH = 40.0

# Temperature — above this, spray can cause phytotoxicity (leaf burn).
# Below this, cold water can shock tropical plants (rare, mainly hill country).
TEMP_SUPPRESS_SPRAY_HIGH_C = 32.0
TEMP_SUPPRESS_SPRAY_LOW_C = 10.0


# ---------------------------------------------------------------------------
# Tools we gate
# ---------------------------------------------------------------------------

# If a tool isn't in this set, the weather gate doesn't apply to it.
# (e.g. reading sensors, querying history, or non-actuator tools)
WEATHER_SENSITIVE_TOOLS = {
    "control_irrigation",
    "schedule_fertigation",
    "spray_chemical",
}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def check_weather(ctx: SafetyContext, tool: str) -> str | None:
    """
    Return a suppression reason if the tool should be blocked due to weather.
    Return None if the weather permits the action.

    This function is deterministic and side-effect-free. It's called from
    validate_tool_call() which handles logging and enforcement.
    """
    if tool not in WEATHER_SENSITIVE_TOOLS:
        return None

    # --- Irrigation ---
    if tool == "control_irrigation":
        if ctx.weather.rain_forecast_mm_6h >= RAIN_SUPPRESS_IRRIGATION_MM:
            return (
                f"rain forecast {ctx.weather.rain_forecast_mm_6h:.1f}mm in next 6h "
                f"(threshold {RAIN_SUPPRESS_IRRIGATION_MM}mm)"
            )
        if ctx.weather.wind_kmh >= WIND_SUPPRESS_IRRIGATION_KMH:
            return (
                f"wind {ctx.weather.wind_kmh:.1f}km/h too high for uniform irrigation "
                f"(threshold {WIND_SUPPRESS_IRRIGATION_KMH}km/h)"
            )

    # --- Fertigation (shares irrigation's rain check; nutrient runoff is
    #     worse than plain water runoff) ---
    if tool == "schedule_fertigation":
        if ctx.weather.rain_forecast_mm_6h >= RAIN_SUPPRESS_SPRAY_MM:
            return (
                f"rain forecast {ctx.weather.rain_forecast_mm_6h:.1f}mm in next 6h — "
                f"fertilizer would wash off / leach into groundwater "
                f"(threshold {RAIN_SUPPRESS_SPRAY_MM}mm)"
            )

    # --- Chemical spray ---
    if tool == "spray_chemical":
        if ctx.weather.rain_forecast_mm_6h >= RAIN_SUPPRESS_SPRAY_MM:
            return (
                f"rain forecast {ctx.weather.rain_forecast_mm_6h:.1f}mm in next 6h — "
                f"chemical would wash off before absorption "
                f"(threshold {RAIN_SUPPRESS_SPRAY_MM}mm)"
            )
        if ctx.weather.wind_kmh >= WIND_SUPPRESS_SPRAY_KMH:
            return (
                f"wind {ctx.weather.wind_kmh:.1f}km/h too high for spray — "
                f"drift risk (threshold {WIND_SUPPRESS_SPRAY_KMH}km/h)"
            )
        if ctx.weather.temp_c >= TEMP_SUPPRESS_SPRAY_HIGH_C:
            return (
                f"temperature {ctx.weather.temp_c:.1f}°C too high for spray — "
                f"phytotoxicity risk (threshold {TEMP_SUPPRESS_SPRAY_HIGH_C}°C)"
            )
        if ctx.weather.temp_c <= TEMP_SUPPRESS_SPRAY_LOW_C:
            return (
                f"temperature {ctx.weather.temp_c:.1f}°C too low for spray — "
                f"cold-shock risk (threshold {TEMP_SUPPRESS_SPRAY_LOW_C}°C)"
            )

    return None