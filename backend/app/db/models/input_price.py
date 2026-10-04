"""
InputPrice — curated LKR prices for agricultural inputs.

Design:
- tenant_id NULL means "global catalog" (admin-curated, shared across tenants).
  A non-null tenant_id is a tenant-specific override (their actual invoice).
- valid_from / valid_until gives price history. Look up by date.
- source field tracks provenance: 'HARTI', 'admin', 'tenant invoice', 'seed'.

The vision model's estimated_cost_lkr is a guess. THIS table is the source
of truth for real cost calculations (Phase 8c).

    ⚠️  The seed values are PLACEHOLDERS. Before production use, replace
    them with current prices from HARTI (Hector Kobbekaduwa Agrarian
    Research and Training Institute) or verified supplier invoices.
"""
import enum
import uuid
from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, ForeignKey, Numeric, func, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InputCategory(str, enum.Enum):
    FUNGICIDE = "fungicide"
    INSECTICIDE = "insecticide"
    HERBICIDE = "herbicide"
    FERTILIZER = "fertilizer"
    WATER = "water"
    LABOR = "labor"
    ENERGY = "energy"
    FUEL = "fuel"
    SEED = "seed"
    OTHER = "other"


class InputPrice(Base):
    __tablename__ = "input_prices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # NULL = global catalog. Non-null = tenant-specific override.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    category: Mapped[InputCategory] = mapped_column(
        SAEnum(InputCategory, name="input_category"),
        nullable=False,
        index=True,
    )

    # Human-readable, e.g. "Copper oxychloride 50% WP"
    product_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Normalized for lookup, e.g. "copper_oxychloride"
    active_ingredient: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )

    # Unit of measure: 'kg', 'L', 'hr', 'kWh', 'bag_50kg', etc.
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    price_lkr: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    region: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LK", server_default="LK"
    )

    # Time validity — enables historical cost lookups
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Where this price came from. Trust signal for the calculation.
    source: Mapped[str] = mapped_column(String(120), nullable=False)

    # Admin flag — has a human verified this?
    verified: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<InputPrice {self.product_name!r} {self.price_lkr} LKR/{self.unit}"
            f" tenant={self.tenant_id or 'GLOBAL'}>"
        )