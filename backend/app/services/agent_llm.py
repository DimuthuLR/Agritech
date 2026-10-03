"""
LLM agent — uses Phi-4-mini via Ollama to make decisions.

Same interface as agent_mock.decide(): takes a SafetyContext, returns
an AgentDecision. Everything upstream (agent_loop, gate, audit) is
unchanged.

Character baked into the prompt:
    CONSERVATIVE · TRANSPARENT · CONSISTENT · HUMBLE

Uses Ollama's OpenAI-compatible endpoint at http://localhost:11434/v1.
Swapping to a different model or hosted provider is one line of config.
"""
import json
import logging
from dataclasses import dataclass

from openai import OpenAI

from app.core.safety.context import SafetyContext


log = logging.getLogger(__name__)


# --- Configuration ----------------------------------------------------------

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"
MODEL_NAME = "qwen2.5:7b-instruct-q4_K_M"

PROMPT_VERSION = "agent_llm@6"   # bumped: enriched_context replaces history_text
MODEL_TAG = "qwen2.5-7b"

# --- Client (singleton) ------------------------------------------------------

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
    return _client


# --- Decision dataclass ------------------------------------------------------

@dataclass(frozen=True)
class AgentDecision:
    tool: str
    args: dict
    reason: str


# --- System prompt ----------------------------------------------------------

SYSTEM_PROMPT = """You are an agricultural irrigation advisor for a Sri Lankan horticulture farm.

Your job: decide whether to irrigate, fertigate, spray, or do nothing for a plot, right now.

CHARACTER — follow these principles strictly:

1. CONSERVATIVE
   If uncertain, do less. Never propose more water, nutrients, or chemicals
   than clearly needed. Under-irrigation is a recoverable problem; over-
   irrigation causes root rot, nutrient leaching, and crop loss.

   BUT: conservative does not mean passive. If soil moisture is CLEARLY
   below the target range for the crop and stage, act — a small pulse is
   the correct choice. Do not let a favorable 30-day trend override a
   clearly dry current reading. The 30-day trend tells you whether the
   soil has deep reserves; the current reading tells you what the plant
   needs right now. When they conflict and the reading is clearly low,
   trust the reading.

2. TRANSPARENT
   Every decision must include a one-sentence reason in plain English that
   a farmer without technical training could understand. Do not use jargon
   without explaining it.

3. CONSISTENT
   The same situation should produce the same decision. Base your reasoning
   on the state and history provided, not on speculation.

4. HUMBLE
   If sensor data is missing or stale (older than 30 minutes), or if you
   are uncertain, return noop. It is always acceptable to do nothing.

TOOLS YOU MAY PROPOSE:

  control_irrigation   — pulse irrigation
      args: { "duration_min": <integer, minutes> }

  schedule_fertigation — nutrient delivery via irrigation
      args: { "duration_min": <integer>, "ec_target": <float, mS/cm> }

  spray_chemical       — pesticide or fungicide application
      args: { "dose_ml_per_ha": <float> }

  noop                 — do nothing this cycle
      args: { "reason": "<why no action is appropriate>" }

CONSTRAINTS:
- You do NOT have authority to exceed safety limits. A separate gate will
  reject out-of-bounds proposals. If unsure of a safe value, use a small
  conservative number or return noop.
- Sri Lankan context: monsoon season, tropical crops (tomato, chili, etc.),
  poly-tunnel and open-field drip systems.

OUTPUT FORMAT:
Respond with a single JSON object. No prose outside the JSON.

{
  "tool": "<one of: control_irrigation, schedule_fertigation, spray_chemical, noop>",
  "args": { ... },
  "reason": "<one sentence, plain English>"
}
"""


# --- Context → prompt formatting --------------------------------------------

def _format_context(ctx: SafetyContext) -> str:
    """Render the SafetyContext as a compact text block for the prompt."""
    from app.core.safety.limits_matrix import get_limits

    sm = ctx.sensors.soil_moisture
    sm_str = f"{sm:.3f}" if sm is not None else "no data"
    age_min = ctx.sensors.newest_reading_age_s / 60.0

    # Provide the target range so the model has an explicit reference.
    limits = get_limits(ctx.crop, ctx.stage, ctx.soil_type, ctx.region)
    if limits is not None:
        tmin = limits.target_soil_moisture_min
        tmax = limits.target_soil_moisture_max
        if sm is None:
            verdict = "no reading"
        elif sm < tmin:
            verdict = f"BELOW target (deficit {tmin - sm:.3f})"
        elif sm > tmax:
            verdict = f"ABOVE target (excess {sm - tmax:.3f})"
        else:
            verdict = "WITHIN target"

        target_line = (
            f"    Target range for {ctx.crop} ({ctx.stage.value}): "
            f"{tmin:.2f} – {tmax:.2f}\n"
            f"    Verdict: {verdict}"
        )
        bounds_line = (
            f"\n  Operating envelope (safety limits — proposals outside this range will be rejected):\n"
            f"    Max duration per irrigation event: {limits.max_minutes_per_event} minutes\n"
            f"    Max events per 24h: {limits.max_events_per_day}\n"
            f"    Minimum gap between events: {limits.min_minutes_between} minutes\n"
            f"    Max daily water budget: {limits.max_daily_L_per_ha:.0f} L/ha"
        )
    else:
        target_line = "    Target range: (not configured for this crop/stage)"
        bounds_line = ""

    return f"""CURRENT PLOT STATE:

  Crop: {ctx.crop}
  Growth stage: {ctx.stage.value}
  Soil/growing medium: {ctx.soil_type.value}
  Region: {ctx.region.value}

  Weather (now):
    Temperature: {ctx.weather.temp_c:.1f} °C
    Wind: {ctx.weather.wind_kmh:.1f} km/h
    Rain forecast (next 6h): {ctx.weather.rain_forecast_mm_6h:.1f} mm

  Sensors (latest):
    Soil moisture: {sm_str} (0.0 = bone dry, 1.0 = saturated)
{target_line}
    Sensor age: {age_min:.0f} minutes
{bounds_line}

  Recent irrigation history:
    Events in last 24h: {ctx.irrigation_events_today}
    Last irrigation: {ctx.last_irrigation_at.isoformat() if ctx.last_irrigation_at else "never"}
"""

# --- Main entry point -------------------------------------------------------

def decide(ctx: SafetyContext, enriched_context: str = "") -> AgentDecision:
    """
    Ask Phi-4-mini for a decision. Returns an AgentDecision.

    `enriched_context` is optional caller-composed text containing any
    additional reasoning material — recent decisions (RAG), trend data,
    domain knowledge. The caller formats it; this function includes it
    verbatim in the prompt.

    On any failure (network, malformed JSON, unknown tool), returns a
    safe noop with an explanation. The agent loop never crashes because
    the model misbehaved.
    """
    client = _get_client()

    context_block = ""
    if enriched_context:
        context_block = "\n\n" + enriched_context

    user_prompt = (
        _format_context(ctx)
        + context_block
        + "\n\nDecide the next action. Respond with JSON only."
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500,
        )
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        return AgentDecision(
            tool="noop",
            args={},
            reason=f"LLM unavailable ({type(e).__name__}); deferring to human.",
        )

    raw = response.choices[0].message.content or ""
    return _parse_response(raw)


# --- Response parsing -------------------------------------------------------

VALID_TOOLS = {
    "control_irrigation",
    "schedule_fertigation",
    "spray_chemical",
    "noop",
}


def _parse_response(raw: str) -> AgentDecision:
    """Parse the model's JSON output into an AgentDecision. Safe fallback on failure."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning(f"Model returned non-JSON: {raw[:200]!r}")
        return AgentDecision(
            tool="noop",
            args={},
            reason="Model returned malformed output; deferring to human.",
        )

    tool = data.get("tool")
    args = data.get("args") or {}
    reason = data.get("reason") or "(no reason provided)"

    if tool not in VALID_TOOLS:
        log.warning(f"Model proposed unknown tool {tool!r}")
        return AgentDecision(
            tool="noop",
            args={},
            reason=f"Model proposed unrecognized action {tool!r}; deferring to human.",
        )

    if not isinstance(args, dict):
        args = {}

    return AgentDecision(tool=tool, args=args, reason=str(reason))