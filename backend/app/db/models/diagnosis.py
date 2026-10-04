"""
Diagnosis — a plant disease diagnosis from an uploaded image.

Lifecycle:
    pending → (AgriGemma processes) → complete
                                    ↘ failed

Teacher-mode output stored:
    - disease, confidence, severity
    - what_is_happening (biology explanation)
    - treatment_steps (this week)
    - prevention_next_season (cultural)
    - estimated_cost_lkr

Image handling:
    - image_hash (sha256) prevents duplicate calls — same image = same result
    - image_path is the on-disk location (tenant-isolated)
    - Original file may be deleted after N days; hash + diagnosis persist
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Image
    image_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    image_size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)

    # Status
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Diagnosis result
    disease: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Teacher-mode content
    what_is_happening: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    prevention_next_season: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    estimated_cost_lkr: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cross-links
    requires_chemical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    proposed_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Provenance
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Diagnosis {self.id} status={self.status} disease={self.disease}>"