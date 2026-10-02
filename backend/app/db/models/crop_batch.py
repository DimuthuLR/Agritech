"""
CropBatch — one planting cycle on a plot.

A plot can have a sequence of crop batches over time: tomato → lettuce → tomato.
Each has its own dates, expected yield, and financials.
"""
import uuid
from datetime import datetime, date
from sqlalchemy import String, Date, DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CropBatch(Base):
    __tablename__ = "crop_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True
    )

    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    variety: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Timeline
    planted_at: Mapped[date] = mapped_column(Date, nullable=False)
    expected_harvest_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    harvested_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Yield
    expected_yield_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_yield_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CropBatch {self.crop!r} plot={self.plot_id}>"