"""
Diagnosis service — calls the vision model to diagnose plant disease.

Architecture:
    Image bytes → base64 → vision model (llama-server, Gemma 3)
    → structured JSON (teacher-mode) → Diagnosis row

Design principles:
- Same abstraction as agent_llm: the model is swappable via config.
- Teacher-mode: the output explains the WHY, not just the WHAT. Farmers
  learn, they don't just comply.
- Conservative on chemicals: any recommendation to spray requires human
  approval (enforced by the safety gate when we create the task in 7f).
- Structured output: we ask for JSON and validate it before trusting it.
- Fail-safe: model unavailability produces a 'failed' diagnosis, never a crash.
"""
import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.diagnosis import Diagnosis


log = logging.getLogger(__name__)


# --- Configuration ----------------------------------------------------------

PROMPT_VERSION = "diagnosis_v1"
MODEL_TAG = "gemma-3-4b"
MAX_TOKENS = 800


# --- Client (singleton) -----------------------------------------------------

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.llama_server_url,
            api_key=settings.llama_server_api_key,
        )
    return _client


# --- Output type ------------------------------------------------------------

@dataclass
class DiagnosisResult:
    """Structured output from the vision model."""
    disease: str
    confidence: float
    severity: str
    what_is_happening: str
    treatment_steps: list[str]
    prevention_next_season: list[str]
    estimated_cost_lkr: float
    requires_chemical: bool
    raw_response: str = ""      # for audit / debugging
    model: str = MODEL_TAG
    prompt_version: str = PROMPT_VERSION


# --- System prompt (teacher-mode) -------------------------------------------

SYSTEM_PROMPT = """You are a plant pathologist advising a Sri Lankan farmer.

Your job: analyze a photograph of a crop leaf and provide a TEACHER-MODE diagnosis.

TEACHER-MODE means you explain:

1. WHAT you see (the disease or condition, with confidence)
2. WHY it happens (the biology — what the pathogen is doing, what conditions favor it)
3. WHAT to do this week (concrete treatment steps)
4. HOW to prevent it next season (cultural and management practices)
5. HOW MUCH it will cost to treat (estimate in Sri Lankan Rupees, LKR)

CHARACTER:
- HONEST: if the image is unclear, low confidence, or shows a healthy plant, say so.
- CONSERVATIVE: prefer cultural/mechanical controls over chemicals where possible.
- SPECIFIC: cite symptom details from the image, not generic descriptions.
- LOCAL: reference Sri Lankan conditions (monsoon seasons, common varieties,
  locally available treatments) where relevant.

CHEMICALS:
- Only recommend chemical treatment if the disease clearly warrants it.
- If you recommend a chemical, set "requires_chemical": true.
- Estimate the cost of the full treatment in LKR.

OUTPUT FORMAT:
Respond with a single JSON object. No prose outside the JSON.

{
  "disease": "<name, or 'Healthy' or 'Uncertain'>",
  "confidence": <0.0-1.0>,
  "severity": "<none|low|moderate|high>",
  "what_is_happening": "<2-3 sentences explaining the biology>",
  "treatment_steps": ["<step 1>", "<step 2>", ...],
  "prevention_next_season": ["<practice 1>", "<practice 2>", ...],
  "estimated_cost_lkr": <number>,
  "requires_chemical": <true|false>
}
"""


def _build_user_prompt(plot_crop: str | None, notes: str | None) -> str:
    parts = ["Please diagnose the plant disease visible in this image."]
    if plot_crop:
        parts.append(f"Context: this is a {plot_crop} crop.")
    if notes:
        parts.append(f"Farmer's notes: {notes}")
    parts.append("Respond with JSON only.")
    return " ".join(parts)


# --- Core function ----------------------------------------------------------

def diagnose_image(
    image_bytes: bytes,
    plot_crop: str | None = None,
    notes: str | None = None,
) -> DiagnosisResult:
    """
    Send image to the vision model, get back a structured diagnosis.

    Raises DiagnosisError on unrecoverable failure (model unavailable,
    unparseable output). Caller should catch this and mark the diagnosis
    row as 'failed'.
    """
    client = _get_client()

    b64 = base64.b64encode(image_bytes).decode("ascii")

    user_prompt = _build_user_prompt(plot_crop, notes)

    try:
        response = client.chat.completions.create(
            model=settings.vision_model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            max_tokens=MAX_TOKENS,
            temperature=0.2,
        )
    except Exception as e:
        raise DiagnosisError(f"Vision model call failed: {e}") from e

    raw = response.choices[0].message.content or ""
    return _parse_response(raw)


def _parse_response(raw: str) -> DiagnosisResult:
    """Parse the model's JSON output. Raises DiagnosisError on failure."""
    # The model sometimes wraps JSON in markdown fences despite instructions.
    # Strip them if present.
    text = raw.strip()
    if text.startswith("```"):
        # Remove leading ```json or ```
        first_newline = text.find("\n")
        if first_newline > 0:
            text = text[first_newline + 1:]
        # Remove trailing ```
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise DiagnosisError(
            f"Model returned non-JSON: {raw[:200]!r}"
        ) from e

    required = {
        "disease", "confidence", "severity",
        "what_is_happening", "treatment_steps",
        "prevention_next_season", "estimated_cost_lkr",
        "requires_chemical",
    }
    missing = required - set(data.keys())
    if missing:
        raise DiagnosisError(f"Model output missing keys: {missing}")

    # Normalize some types
    try:
        confidence = float(data["confidence"])
        if confidence > 1.0:
            confidence = confidence / 100.0  # accept 0-100 scale
        cost = float(data.get("estimated_cost_lkr") or 0)
        treatment = data.get("treatment_steps") or []
        prevention = data.get("prevention_next_season") or []
        if not isinstance(treatment, list):
            treatment = [str(treatment)]
        if not isinstance(prevention, list):
            prevention = [str(prevention)]

        return DiagnosisResult(
            disease=str(data["disease"])[:200],
            confidence=max(0.0, min(1.0, confidence)),
            severity=str(data["severity"])[:32],
            what_is_happening=str(data["what_is_happening"]),
            treatment_steps=[str(t) for t in treatment],
            prevention_next_season=[str(t) for t in prevention],
            estimated_cost_lkr=cost,
            requires_chemical=bool(data["requires_chemical"]),
            raw_response=raw,
        )
    except (TypeError, ValueError) as e:
        raise DiagnosisError(f"Bad field types in model output: {e}") from e


# --- Exception --------------------------------------------------------------

class DiagnosisError(Exception):
    """Raised when a diagnosis cannot be completed."""
    pass


# --- Persistence ------------------------------------------------------------

def run_and_store_diagnosis(
    db: Session,
    diagnosis_id: UUID,
    image_bytes: bytes,
    plot_crop: str | None,
    notes: str | None,
) -> Diagnosis:
    """
    Run the vision model and update the Diagnosis row in place.

    This is designed to be called synchronously for now, or from a
    background worker in a later phase. Either way, the row is the
    source of truth — we update status='complete' or 'failed'.
    """
    diag = db.get(Diagnosis, diagnosis_id)
    if diag is None:
        raise DiagnosisError(f"Diagnosis {diagnosis_id} not found")

    try:
        result = diagnose_image(image_bytes, plot_crop, notes)
    except DiagnosisError as e:
        diag.status = "failed"
        diag.error = str(e)
        diag.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise

    diag.status = "complete"
    diag.disease = result.disease
    diag.confidence = result.confidence
    diag.severity = result.severity
    diag.what_is_happening = result.what_is_happening
    diag.treatment_steps = result.treatment_steps
    diag.prevention_next_season = result.prevention_next_season
    diag.estimated_cost_lkr = result.estimated_cost_lkr
    diag.requires_chemical = result.requires_chemical
    diag.model = result.model
    diag.prompt_version = result.prompt_version
    diag.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(diag)
    return diag