"""
Chat endpoint — conversational Qwen with full context.

This is Layer 1 of the three-layer model from the master outline:
a natural-language interface that uses the same enriched context
(RAG history, trends, weather, agronomy, overrides) that the decision
agent uses, but returns prose instead of tool calls.

The chat NEVER triggers actuator commands. If the user asks for an
action, the response suggests opening a task or check the tasks page.

Sessions are stateless for MVP. Conversation history is kept on the
client and echoed back on each request. Phase 10b will add a
`chat_sessions` table for persistent history.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role
from app.core.config import settings
from app.db.models.plot import Plot
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.services.agent_history import (
    fetch_overrides_context,
    fetch_recent_decisions,
    format_decisions_for_prompt,
)
from app.services.agronomy import (
    compute_agronomic_summary,
    format_agronomy_for_prompt,
)
from app.services.context_builder import build_safety_context
from app.services.trends import (
    fetch_soil_moisture_trend,
    format_trend_for_prompt,
)
from app.services.weather_history import (
    DEFAULT_LAT,
    fetch_weather_history,
    format_weather_history_for_prompt,
)


log = logging.getLogger(__name__)


router = APIRouter(prefix="/chat", tags=["chat"])


OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_API_KEY = settings.ollama_api_key
MODEL_NAME = "qwen2.5:7b-instruct-q4_K_M"


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """A single turn in the conversation."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    plot_id: UUID | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Sri Lankan farm advisor. You answer farmer questions in plain, friendly English.

CHARACTER — same as the decision agent:
- CONSERVATIVE: recommend less intervention, not more.
- TRANSPARENT: explain your reasoning. Cite the data you're using.
- CONSISTENT: base answers on provided context.
- HUMBLE: if you don't know, say so. Suggest consulting a local extension officer for anything uncertain.

RULES:
1. You CANNOT execute actions. If the farmer asks you to irrigate, spray,
   or change something, explain what you would recommend and tell them to
   use the Tasks page to approve a proposal, or the Manual Control panel
   to take action themselves.
2. Base your answers on the PLOT CONTEXT provided. Do not invent sensor
   readings, weather, or history.
3. Keep answers concise — 2-4 sentences unless the question clearly
   requires more detail. Farmers read on phones.
4. Sri Lankan context: monsoon seasons, local crops (tomato, chili,
   brinjal, cabbage, carrot), local practices.
5. If the question is outside agriculture, politely redirect.

STYLE:
- Plain English. No jargon unless you explain it.
- Cite specific numbers when you have them ("soil moisture is 0.28, below the 0.30 target").
- Use LKR for any cost mentions.
"""


# ---------------------------------------------------------------------------
# Context builder for chat
# ---------------------------------------------------------------------------

def _build_chat_context(db: Session, plot_id: UUID) -> str:
    """
    Assemble the same enriched context the decision agent uses.
    Returns a text block; empty string if no plot specified.
    """
    from app.db.models.plot import Plot as PlotModel
    plot = db.get(PlotModel, plot_id)
    if plot is None:
        return ""

    parts: list[str] = []

    # Current state (sensors, weather)
    try:
        ctx = build_safety_context(db, plot_id)
        parts.append(
            f"CURRENT PLOT STATE:\n"
            f"  Plot: {plot.name} ({plot.area_ha} ha)\n"
            f"  Crop: {plot.crop or 'unassigned'} / stage: {plot.stage or '—'}\n"
            f"  Soil: {plot.soil_type or 'unknown'}\n"
            f"  Weather: {ctx.weather.temp_c:.1f}°C, "
            f"{ctx.weather.wind_kmh:.1f}km/h wind, "
            f"{ctx.weather.rain_forecast_mm_6h:.1f}mm rain (next 6h)\n"
            f"  Soil moisture: "
            f"{ctx.sensors.soil_moisture if ctx.sensors.soil_moisture is not None else 'no reading'}\n"
            f"  Last irrigation: "
            f"{ctx.last_irrigation_at.isoformat() if ctx.last_irrigation_at else 'never'}"
        )
    except Exception as e:
        log.warning(f"Chat: context build failed for plot {plot_id}: {e}")

    # Recent decisions
    recent = fetch_recent_decisions(db, plot_id, limit=5)
    history_text = format_decisions_for_prompt(recent)
    if history_text:
        parts.append("RECENT DECISIONS:\n" + history_text)

    # Overrides
    overrides_text = fetch_overrides_context(db, plot_id, limit=5)
    if overrides_text:
        parts.append(overrides_text)

    # 7-day trend
    trend = fetch_soil_moisture_trend(db, plot_id, days=7)
    trend_text = format_trend_for_prompt(trend)
    if trend_text:
        parts.append(trend_text)

    # 30-day weather
    wx_hist = fetch_weather_history(plot.latitude, plot.longitude, days=30)
    wx_text = format_weather_history_for_prompt(wx_hist)
    if wx_text:
        parts.append(wx_text)

    # Agronomy
    if wx_hist and wx_hist.daily:
        lat = plot.latitude if plot.latitude is not None else DEFAULT_LAT
        agro = compute_agronomic_summary(wx_hist.daily, lat, plot.crop or "")
        agro_text = format_agronomy_for_prompt(agro)
        if agro_text:
            parts.append(agro_text)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/message", response_model=ChatResponse)
def send_message(
    payload: ChatRequest,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """
    Send a message to the assistant.

    If plot_id is provided, the full enriched context for that plot is
    included. Otherwise, the assistant answers without plot context.
    """
    # Verify plot ownership if specified
    if payload.plot_id is not None:
        plot = (
            db.query(Plot)
            .filter(Plot.id == payload.plot_id, Plot.tenant_id == user.tenant_id)
            .first()
        )
        if plot is None:
            raise HTTPException(status_code=404, detail="Plot not found")
        context_block = _build_chat_context(db, payload.plot_id)
    else:
        context_block = ""

    # Compose the system prompt with context
    system = SYSTEM_PROMPT
    if context_block:
        system += f"\n\n{context_block}"

    # Build the message list for Qwen
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in payload.history[-10:]:  # cap to last 10 turns
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": payload.message})

    # Call Qwen
    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.3,
            max_tokens=600,
        )
    except Exception as e:
        log.error(f"Chat LLM call failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Assistant unavailable: {type(e).__name__}",
        )

    text = resp.choices[0].message.content or ""
    return ChatResponse(response=text.strip())