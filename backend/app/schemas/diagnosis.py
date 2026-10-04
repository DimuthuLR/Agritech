"""
Pydantic schemas for the diagnosis resource.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DiagnosisRequest(BaseModel):
    """Metadata that comes alongside the image upload."""
    plot_id: uuid.UUID
    notes: str | None = Field(
        None,
        max_length=500,
        description="Optional farmer notes, e.g. 'leaves yellowing for 3 days'",
    )


class DiagnosisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plot_id: uuid.UUID
    image_hash: str
    image_path: str

    status: str                          # 'pending' | 'complete' | 'failed'
    disease: str | None
    confidence: float | None
    severity: str | None

    # Teacher-mode fields
    what_is_happening: str | None
    treatment_steps: list[str] | None
    prevention_next_season: list[str] | None
    estimated_cost_lkr: float | None

    # Cross-links
    model: str | None                    # which model produced this
    prompt_version: str | None
    requires_chemical: bool
    proposed_task_id: uuid.UUID | None   # spray_chemical task if created

    error: str | None
    created_at: datetime
    completed_at: datetime | None