"""
FinancialLedger — a single cost event.

Every task completion posts one or more ledger entries (one per consumed
input category). This gives us per-batch P&L, cost-per-kg, cost-per-plot
queries without scanning tasks and re-deriving costs each time.

Design:
- amount_lkr is pre-computed (qty × unit_price) so reports are fast.
- unit_price_lkr is captured at the moment of the event — if prices change
  later, the historical ledger doesn't silently shift.
- input_price_id links back to the price row used, for audit.
- batch_id may be NULL if no active crop batch on the plot.
- source_task_id is the task that consumed this input.
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Numeric, func, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LedgerCategory(str, enum.Enum):
    """What kind of input cost this is."""
    WATER = "water"
    FERTILIZER = "fertilizer"
    CHEMICAL = "chemical"
    LABOR = "labor"
    ENERGY = "energy"
    FUEL = "fuel"
    SEED = "seed"
    EQUIPMENT = "equipment"
    OTHER = "other"


class FinancialLedger(Base):
    __tablename__ = "financial_ledger"

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

    # May be NULL if no active crop batch on the plot
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crop_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The task that consumed this input
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # What kind of cost
    category: Mapped[LedgerCategory] = mapped_column(
        SAEnum(LedgerCategory, name="ledger_category"),
        nullable=False,
        index=True,
    )

    # Quantity and unit
    qty: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    # Pricing snapshot — captures the price at the moment of the event
    unit_price_lkr: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    amount_lkr: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    # Link to the price row we used (for audit trail)
    input_price_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("input_prices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Free-form extras: e.g. {"product_name": "Copper oxychloride 50% WP"}
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<LedgerEntry {self.category.value} "
            f"{self.qty}{self.unit} = {self.amount_lkr} LKR>"
        )