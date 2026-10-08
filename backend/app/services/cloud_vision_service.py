"""
Cloud vision service — Gemini for plant disease diagnosis.

Why this exists:
    A local 8B vision model (Qwen3-VL-8B) cannot reliably distinguish
    visually-similar disease pairs like Early Blight vs Bacterial Leaf
    Spot. Gemini Flash, trained on far more plant imagery, gets these
    right at ~95% confidence on our test set.

Design:
    - Same DiagnosisResult output as the local service, so the rest of
      the pipeline (cost calc, spray proposal, multi-shot voting) works
      unchanged.
    - Structured JSON response (response_mime_type="application/json")
      so parsing is deterministic.
    - RAG reference chunks are injected into the prompt exactly as with
      the local model. The cloud model benefits from Sri Lankan context
      just as much.
    - Retries on 503 UNAVAILABLE (Google transient overload) with a
      short backoff. Falls back to a secondary model after retries.
    - Any failure that survives retries raises CloudVisionError, which
      the caller catches and falls back to the local Qwen3-VL.
"""
import json
import logging
import time

from google import genai
from google.genai import types

from app.core.config import settings


log = logging.getLogger(__name__)


# Model preference order. First entry is preferred. We cascade on
# persistent 503s from the previous entry. Both must be multimodal
# (accept images) and on the free tier.
GEMINI_MODELS = [
    "gemini-3.8-flash",      # newest, most capable
    "gemini-3.5-flash",      # slightly older, stable
    "gemini-3-flash-preview", # preview of v3
    "gemini-2.5-flash",      # well-established, extremely stable
    "gemini-flash-latest",   # alias — often overloaded
    "gemini-3.1-flash-lite", # last resort before local fallback
]

# How many times to retry a single model on 503 before cascading.
MAX_RETRIES_PER_MODEL = 2
# Seconds between retries.
RETRY_DELAY = 2.0


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise CloudVisionError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


class CloudVisionError(Exception):
    """Raised when cloud vision fails. Caller should fall back to local."""
    pass


# --- Prompt -----------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are a plant pathologist advising a Sri Lankan farmer.

Analyze the attached crop leaf image and respond with a JSON object
matching this exact schema (no prose outside the JSON):

{
  "disease": "<name, or 'Healthy' or 'Uncertain'>",
  "confidence": <0.0-1.0>,
  "severity": "<none|low|moderate|high>",
  "what_is_happening": "<2-3 sentences explaining the biology and why you chose this diagnosis over similar candidates>",
  "treatment_steps": ["<step 1>", "<step 2>", ...],
  "prevention_next_season": ["<practice 1>", "<practice 2>", ...],
  "estimated_cost_lkr": <number>,
  "requires_chemical": <true|false>,
  "recommended_chemical": {
    "active_ingredient": "<snake_case name>" | null,
    "dose_ml_per_ha": <number> | null
  } | null
}

Guidelines:
- Prefer cultural/mechanical controls over chemicals where possible.
- Use active-ingredient names in snake_case (e.g. "mancozeb", "copper_oxychloride").
- Estimate treatment cost in Sri Lankan Rupees as a rough ballpark.
- If the image is unclear or shows a healthy plant, say so honestly.
- Reference Sri Lankan conditions (monsoon seasons, local crops) where relevant.
- Cite specific symptom details from the image, not generic descriptions.

In the "what_is_happening" field, briefly explain WHY you chose this
diagnosis over visually similar candidates (e.g. why Early Blight rather
than Bacterial Leaf Spot).
"""


def _build_user_prompt(plot_crop: str | None, notes: str | None, reference_chunks: str) -> str:
    parts = ["Diagnose the plant disease in this leaf image."]
    if plot_crop:
        parts.append(f"Crop: {plot_crop}.")
    if notes:
        parts.append(f"Farmer's notes: {notes}")
    if reference_chunks.strip():
        parts.append(
            "\n\nREFERENCE MATERIAL (extracts from Sri Lankan agricultural "
            "guides, may be in Sinhala):\n\n" + reference_chunks + "\n\n"
            "Prefer the reference material over general training for Sri "
            "Lankan crops and locally-approved treatments. If the reference "
            "contradicts your instinct, the reference wins."
        )
    return " ".join(parts)


# --- Internal: call one model with retries ----------------------------------

def _call_gemini_once(
    client: genai.Client,
    model_name: str,
    image_bytes: bytes,
    user_prompt: str,
) -> str:
    """
    Call one Gemini model with retries on 503.
    Returns the raw response text. Raises the last exception on failure.
    """
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES_PER_MODEL + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    user_prompt,
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.2,
                    max_output_tokens=1500,
                    response_mime_type="application/json",
                ),
            )
            return (response.text or "").strip()
        except Exception as e:
            last_error = e
            msg = str(e)
            is_503 = "503" in msg or "UNAVAILABLE" in msg
            if is_503 and attempt < MAX_RETRIES_PER_MODEL:
                log.warning(
                    f"Gemini {model_name} returned 503 "
                    f"(attempt {attempt + 1}/{MAX_RETRIES_PER_MODEL + 1}), "
                    f"retrying in {RETRY_DELAY}s…"
                )
                time.sleep(RETRY_DELAY)
                continue
            # Non-retryable error, or retries exhausted — raise
            raise

    # Unreachable — the loop always returns or raises. Belt and suspenders.
    raise last_error or CloudVisionError(f"All retries failed for {model_name}")


# --- Public API -------------------------------------------------------------

def diagnose_cloud(
    image_bytes: bytes,
    plot_crop: str | None = None,
    notes: str | None = None,
    reference_chunks: str = "",
):
    """
    Call Gemini for a diagnosis.

    Returns a DiagnosisResult (parsed by the caller). Raises
    CloudVisionError if every model in the cascade fails.
    """
    from app.services.diagnosis_service import DiagnosisResult, PROMPT_VERSION

    client = _get_client()

    user_prompt = _build_user_prompt(plot_crop, notes, reference_chunks)

    # Cascade through the model preference list.
    text = ""
    used_model = ""
    last_error: Exception | None = None

    for model_name in GEMINI_MODELS:
        try:
            text = _call_gemini_once(client, model_name, image_bytes, user_prompt)
            used_model = model_name
            break
        except Exception as e:
            last_error = e
            log.warning(f"Gemini {model_name} failed: {e}")
            # Try the next model in the cascade.
            continue

    if not text:
        raise CloudVisionError(
            f"All Gemini models failed. Last error: {last_error}"
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CloudVisionError(f"Gemini returned non-JSON: {text[:200]!r}") from e

    # Validate required fields
    required = {
        "disease", "confidence", "severity",
        "what_is_happening", "treatment_steps",
        "prevention_next_season", "estimated_cost_lkr",
        "requires_chemical",
    }
    missing = required - set(data.keys())
    if missing:
        raise CloudVisionError(f"Gemini response missing fields: {missing}")

    # Normalize confidence to 0..1
    confidence = float(data["confidence"])
    if confidence > 1.0:
        confidence = confidence / 100.0

    # Parse the chemical block
    ingredient: str | None = None
    dose: float | None = None
    chem = data.get("recommended_chemical")
    if isinstance(chem, dict):
        ing = chem.get("active_ingredient")
        if isinstance(ing, str) and ing.strip():
            ingredient = ing.strip().lower().replace(" ", "_")
        d = chem.get("dose_ml_per_ha")
        if isinstance(d, (int, float)) and d > 0:
            dose = float(d)

    return DiagnosisResult(
        disease=str(data["disease"])[:200],
        confidence=max(0.0, min(1.0, confidence)),
        severity=str(data["severity"])[:32],
        what_is_happening=str(data["what_is_happening"]),
        treatment_steps=[str(t) for t in (data.get("treatment_steps") or [])],
        prevention_next_season=[str(t) for t in (data.get("prevention_next_season") or [])],
        estimated_cost_lkr=float(data.get("estimated_cost_lkr") or 0),
        requires_chemical=bool(data.get("requires_chemical")),
        recommended_ingredient=ingredient,
        recommended_dose_ml_per_ha=dose,
        raw_response=text,
        model=used_model,
        prompt_version=PROMPT_VERSION,
    )