"""
Chat endpoints — conversational Qwen assistant with persistent sessions
and live-state reconciliation.

Three things to understand about this file:

1. SESSION MODE vs STATELESS MODE
   Two ways to call /chat/message:
     - With session_id → history loaded from DB, persisted after each turn.
     - Without session_id → caller passes history in the request body.

2. LIVE-STATE RECONCILIATION
   Chat is a log, not a plan. Every request injects a "CURRENT SYSTEM
   STATE" block (active tasks, recent activity, live sensors) alongside
   the conversation. The system prompt tells the model that SYSTEM STATE
   always beats CONVERSATION when they conflict. This prevents the AI
   from referencing plans that were never acted on, rejected, or cancelled.

3. STUCK TASK DETECTION
   Tasks that have been in a mid-flow state too long get a ⚠ STUCK marker
   in the SYSTEM STATE block. The model then surfaces them proactively
   ("You have a spray task from 3 days ago that hasn't been actioned").

Feature flag: 'chat' gates the endpoints.
"""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAI
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role, require_feature
from app.core.config import settings
from app.db.models.chat_session import ChatSession
from app.db.models.diagnosis import Diagnosis
from app.db.models.field_event import FieldEvent
from app.db.models.plot import Plot
from app.db.models.task import Task, TaskStatus
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionRead,
    ChatSessionUpdate,
    ChatSessionWithMessages,
)
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

MAX_SESSION_MESSAGES = 50  # hard cap on stored turns per session


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
    return _client


# ============================================================================
# System prompt
# ============================================================================

SYSTEM_PROMPT = """You are a Sri Lankan farm advisor. You answer farmer questions in plain, friendly English.

CHARACTER — same as the decision agent:
- CONSERVATIVE: recommend less intervention, not more.
- TRANSPARENT: explain your reasoning. Cite the data you're using.
- CONSISTENT: base answers on provided context.
- HUMBLE: if you don't know, say so. Never guess.

YOUR QUESTIONS FALL INTO THREE CATEGORIES — apply the right rule:

CATEGORY 1 — FARM-SPECIFIC FACTS
  (weather at their plot, sensor readings, irrigation history, costs,
   decisions we made, tasks, diagnoses)
  → You MUST use only the CURRENT SYSTEM STATE provided below.
  → If the state is missing or does not cover the question, DO NOT
    invent or guess. Say clearly and politely what you need.
  → Never use training data to fill in farm-specific gaps.

CATEGORY 2 — GENERAL AGRICULTURAL KNOWLEDGE
  (what diseases look like, how to prevent them, plant physiology,
   what EC or VPD means, general best practices, treatment concepts)
  → Answer freely from your training. This is what you're for.
  → You may reference Sri Lankan crops and conditions.

CATEGORY 3 — CURRENT EXTERNAL FACTS
  (today's market prices, active outbreak alerts, new regulatory
   announcements, weather outside the selected plot)
  → You cannot check external sources. Politely say so and refer the
    farmer to the Department of Agriculture or an extension officer.

RECONCILIATION — READ THIS CAREFULLY:

You will see two kinds of information:

  1. CONVERSATION SO FAR — what was said earlier in this session.
     Historical. May be stale. May reference plans that were later
     rejected, cancelled, or completed.

  2. CURRENT SYSTEM STATE — what actually exists in the database
     right now. AUTHORITATIVE. Always wins.

When they conflict, CURRENT SYSTEM STATE wins. Specifically:

  - If the conversation mentions a plan or task that does NOT appear
    in ACTIVE PLANS, do not reference it as currently active. Check
    RECENT ACTIVITY to see what happened (rejected, cancelled, done).
    Acknowledge its actual outcome.
  - NEVER re-propose an action solely because it was discussed earlier.
    Always check ACTIVE PLANS first. If a task already exists for that
    action, mention it exists rather than proposing a new one.
  - If a task carries a ⚠ STUCK marker, proactively mention it and ask
    whether the farmer wants to proceed, modify, or cancel it.
  - NEVER assume a plan is still active just because it was discussed.
    Verify against ACTIVE PLANS. If it's not there, it isn't active.

RULES:
1. You CANNOT execute actions. If the farmer asks you to irrigate, spray,
   or change something, explain what you would recommend and tell them to
   use the Tasks page to approve a proposal.
2. NEVER invent sensor readings, weather, costs, or history. If you don't
   have the data, say so politely and specifically.
3. Keep answers concise — 2-4 sentences unless the question clearly
   requires more detail.
4. Sri Lankan context: monsoon seasons, local crops (tomato, chili,
   brinjal, cabbage, carrot), local practices.
5. If the question is entirely outside agriculture, politely redirect.

STYLE:
- Plain English. No jargon unless you explain it.
- Cite specific numbers when you have them ("soil moisture is 0.28").
- Use LKR for cost mentions.
- When refusing, always offer a next step.
"""


# ============================================================================
# Live-state construction
# ============================================================================

def _is_stuck(task: Task, now: datetime) -> bool:
    """A task is stuck if it's been in a mid-flow state too long."""
    age_h = (now - task.created_at).total_seconds() / 3600
    if task.status == TaskStatus.PENDING_APPROVAL and age_h > 48:
        return True
    if task.status == TaskStatus.APPROVED and age_h > 6:
        return True
    if task.status == TaskStatus.DISPATCHED and age_h > 2:
        return True
    if task.status == TaskStatus.ACKED and age_h > 24 * 7:
        return True
    return False


def _build_active_plans(
    db: Session,
    tenant_id: UUID,
    plot_id: UUID | None,
) -> str:
    """
    Active tasks (pending_approval, approved, dispatched, acked).
    Scoped to one plot if plot_id is given, else tenant-wide.
    """
    now = datetime.now(timezone.utc)
    active_statuses = [
        TaskStatus.PENDING_APPROVAL,
        TaskStatus.APPROVED,
        TaskStatus.DISPATCHED,
        TaskStatus.ACKED,
    ]
    q = db.query(Task).filter(
        Task.tenant_id == tenant_id,
        Task.status.in_(active_statuses),
    )
    if plot_id is not None:
        q = q.filter(Task.plot_id == plot_id)

    tasks = q.order_by(desc(Task.created_at)).limit(20).all()

    lines = ["ACTIVE PLANS:"]
    if not tasks:
        lines.append("  (none)")
        return "\n".join(lines)

    for t in tasks:
        age_h = (now - t.created_at).total_seconds() / 3600
        age_str = f"{int(age_h)}h" if age_h < 48 else f"{int(age_h/24)}d"
        marker = "  ⚠ STUCK" if _is_stuck(t, now) else ""
        reason = (t.reason or "")[:120]
        lines.append(
            f"  • {str(t.id)[:8]} — {t.tool} — {t.status.value} "
            f"(age {age_str}){marker}"
        )
    return "\n".join(lines)


def _build_recent_activity(
    db: Session,
    tenant_id: UUID,
    plot_id: UUID | None,
    days: int = 14,
) -> str:
    """
    Chronological log of tasks, diagnoses, and field events.
    Scoped to one plot if plot_id is given.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    entries: list[tuple[datetime, str]] = []

    # Tasks
    q = db.query(Task).filter(
        Task.tenant_id == tenant_id,
        Task.created_at >= since,
    )
    if plot_id is not None:
        q = q.filter(Task.plot_id == plot_id)
    for t in q.order_by(desc(Task.created_at)).limit(20).all():
        entries.append((
            t.created_at,
            f"  {t.created_at.date()} Task {str(t.id)[:8]} — "
            f"{t.tool} — {t.status.value.upper()}",
        ))

    # Diagnoses
    q = db.query(Diagnosis).filter(
        Diagnosis.tenant_id == tenant_id,
        Diagnosis.created_at >= since,
    )
    if plot_id is not None:
        q = q.filter(Diagnosis.plot_id == plot_id)
    for d in q.order_by(desc(Diagnosis.created_at)).limit(15).all():
        conf_str = f" (conf {d.confidence:.2f})" if d.confidence else ""
        entries.append((
            d.created_at,
            f"  {d.created_at.date()} Diagnosis — "
            f"{d.disease or 'unknown'}{conf_str}",
        ))

    # Field events
    q = db.query(FieldEvent).filter(
        FieldEvent.tenant_id == tenant_id,
        FieldEvent.occurred_at >= since,
    )
    if plot_id is not None:
        q = q.filter(FieldEvent.plot_id == plot_id)
    for e in q.order_by(desc(FieldEvent.occurred_at)).limit(15).all():
        outcome = f" [{e.outcome.value}]" if e.outcome else ""
        action = e.action_taken or e.event_type.value
        entries.append((
            e.occurred_at,
            f"  {e.occurred_at.date()} Field event — {action}{outcome}",
        ))

    entries.sort(key=lambda x: x[0], reverse=True)

    lines = [f"RECENT ACTIVITY (last {days} days):"]
    if not entries:
        lines.append("  (no recent activity)")
    else:
        for _, line in entries[:30]:
            lines.append(line)
    return "\n".join(lines)


def _build_live_plot_state(db: Session, plot_id: UUID) -> str:
    """
    Sensors + weather + agronomy for a single plot.
    Returns empty string if the plot doesn't exist.
    """
    plot = db.get(Plot, plot_id)
    if plot is None:
        return ""

    parts: list[str] = []

    try:
        ctx = build_safety_context(db, plot_id)
        parts.append(
            f"LIVE PLOT STATE:\n"
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
        log.warning(f"Chat: live state build failed for plot {plot_id}: {e}")

    recent = fetch_recent_decisions(db, plot_id, limit=5)
    history_text = format_decisions_for_prompt(recent)
    if history_text:
        parts.append("RECENT DECISIONS:\n" + history_text)

    overrides_text = fetch_overrides_context(db, plot_id, limit=5)
    if overrides_text:
        parts.append(overrides_text)

    trend = fetch_soil_moisture_trend(db, plot_id, days=7)
    trend_text = format_trend_for_prompt(trend)
    if trend_text:
        parts.append(trend_text)

    wx_hist = fetch_weather_history(plot.latitude, plot.longitude, days=30)
    wx_text = format_weather_history_for_prompt(wx_hist)
    if wx_text:
        parts.append(wx_text)

    if wx_hist and wx_hist.daily:
        lat = plot.latitude if plot.latitude is not None else DEFAULT_LAT
        agro = compute_agronomic_summary(wx_hist.daily, lat, plot.crop or "")
        agro_text = format_agronomy_for_prompt(agro)
        if agro_text:
            parts.append(agro_text)

    return "\n\n".join(parts)


def _build_system_state_block(
    db: Session,
    tenant_id: UUID,
    plot_id: UUID | None,
) -> str:
    """Assemble the full CURRENT SYSTEM STATE block."""
    parts: list[str] = [
        "=== CURRENT SYSTEM STATE (AUTHORITATIVE — trust this over "
        "CONVERSATION SO FAR) ===",
        "",
        _build_active_plans(db, tenant_id, plot_id),
        "",
        _build_recent_activity(db, tenant_id, plot_id, days=14),
    ]

    if plot_id is not None:
        live = _build_live_plot_state(db, plot_id)
        if live:
            parts.append("")
            parts.append(live)

    return "\n".join(parts)


# ============================================================================
# Session CRUD
# ============================================================================

def _get_owned_session(
    db: Session,
    session_id: UUID,
    user: User,
) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.user_id != user.id or session.tenant_id != user.tenant_id:
        # Same 404 to avoid leaking session existence across users
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post(
    "/sessions",
    response_model=ChatSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: ChatSessionCreate,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Create an empty chat session. Returns the session record."""
    require_feature(db, user.tenant_id, "chat")

    if payload.plot_id is not None:
        plot = (
            db.query(Plot)
            .filter(Plot.id == payload.plot_id, Plot.tenant_id == user.tenant_id)
            .first()
        )
        if plot is None:
            raise HTTPException(status_code=404, detail="Plot not found")

    session = ChatSession(
        tenant_id=user.tenant_id,
        user_id=user.id,
        plot_id=payload.plot_id,
        title=payload.title,
        messages=[],
        message_count=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[ChatSessionRead])
def list_sessions(
    include_archived: bool = False,
    limit: int = 50,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """List the caller's chat sessions, newest activity first."""
    require_feature(db, user.tenant_id, "chat")

    q = db.query(ChatSession).filter(
        ChatSession.tenant_id == user.tenant_id,
        ChatSession.user_id == user.id,
    )
    if not include_archived:
        q = q.filter(ChatSession.is_archived.is_(False))

    # Sort by last_message_at DESC, falling back to created_at for empty ones
    rows = (
        q.order_by(
            desc(ChatSession.last_message_at),
            desc(ChatSession.created_at),
        )
        .limit(min(limit, 200))
        .all()
    )
    return rows


@router.get("/sessions/{session_id}", response_model=ChatSessionWithMessages)
def get_session(
    session_id: UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Full history of one session."""
    require_feature(db, user.tenant_id, "chat")
    return _get_owned_session(db, session_id, user)


@router.patch("/sessions/{session_id}", response_model=ChatSessionRead)
def update_session(
    session_id: UUID,
    payload: ChatSessionUpdate,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Rename or archive a session."""
    require_feature(db, user.tenant_id, "chat")
    session = _get_owned_session(db, session_id, user)

    if payload.title is not None:
        session.title = payload.title
    if payload.is_archived is not None:
        session.is_archived = payload.is_archived

    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Hard-delete a session and its messages."""
    require_feature(db, user.tenant_id, "chat")
    session = _get_owned_session(db, session_id, user)
    db.delete(session)
    db.commit()
    return None


# ============================================================================
# Send message (session-aware)
# ============================================================================

def _derive_title(first_message: str) -> str:
    """Auto-title from the first user message."""
    clean = " ".join(first_message.split())
    return clean[:60] + ("…" if len(clean) > 60 else "")


@router.post("/message", response_model=ChatResponse)
def send_message(
    payload: ChatRequest,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """
    Send a message. Loads history from session (if session_id given) or
    from the request body (legacy stateless mode). Always injects the
    CURRENT SYSTEM STATE block from the DB.
    """
    require_feature(db, user.tenant_id, "chat")

    # --- Resolve session (optional) ---
    session: ChatSession | None = None
    if payload.session_id is not None:
        session = _get_owned_session(db, payload.session_id, user)

    # --- Determine plot (session wins over request) ---
    effective_plot_id = payload.plot_id
    if session is not None and session.plot_id is not None:
        effective_plot_id = session.plot_id

    # Verify plot ownership if specified
    if effective_plot_id is not None:
        plot = (
            db.query(Plot)
            .filter(
                Plot.id == effective_plot_id,
                Plot.tenant_id == user.tenant_id,
            )
            .first()
        )
        if plot is None:
            raise HTTPException(status_code=404, detail="Plot not found")

    # --- Get conversation history ---
    if session is not None:
        raw_history = session.messages or []
        history: list[ChatMessage] = [
            ChatMessage(**m) if isinstance(m, dict) else m
            for m in raw_history
        ]
    else:
        history = payload.history

    # --- Build system prompt with reconciliation ---
    system_state = _build_system_state_block(
        db, user.tenant_id, effective_plot_id
    )
    system = SYSTEM_PROMPT + "\n\n" + system_state

    # --- Assemble messages for Qwen ---
    # Take the last 20 turns (10 exchanges) from history for the actual call.
    # The full DB history stays intact; we just don't blow the context window.
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history[-20:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": payload.message})

    # --- Call Qwen ---
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

    reply_text = (resp.choices[0].message.content or "").strip()
    now = datetime.now(timezone.utc)

    # --- Persist to session if we have one ---
    if session is not None:
        new_turns = [
            {"role": "user", "content": payload.message,
             "created_at": now.isoformat()},
            {"role": "assistant", "content": reply_text,
             "created_at": now.isoformat()},
        ]
        combined = list(session.messages or []) + new_turns

        # Cap the stored history. Keep the first user turn for context and
        # the most recent N-1. Older middle turns are dropped.
        if len(combined) > MAX_SESSION_MESSAGES:
            first = combined[0]
            recent = combined[-(MAX_SESSION_MESSAGES - 1):]
            combined = [first] + recent

        session.messages = combined
        session.message_count = len(combined)
        session.last_message_at = now
        if session.title is None:
            session.title = _derive_title(payload.message)

        db.commit()
        db.refresh(session)

    return ChatResponse(
        response=reply_text,
        session_id=session.id if session else None,
        message_count=session.message_count if session else None,
    )