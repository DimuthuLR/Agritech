"""
Ledger service — cost calculation and posting.

Every completed task posts one or more ledger entries (one per consumed
input category: water, energy, chemical, fertilizer, labor).

Design:
- Best-effort posting. Failures are logged but don't roll back task state.
- Snapshots the unit price at posting time — cost history doesn't drift.
- Amount is pre-computed for fast aggregation queries.
- Batch allocation: uses the plot's currently-active crop_batch if any.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.crop_batch import CropBatch
from app.db.models.financial_ledger import FinancialLedger, LedgerCategory
from app.db.models.input_price import InputCategory, InputPrice
from app.db.models.plot import Plot
from app.db.models.task import Task
from app.services import agricultural_constants as const
from app.services.pricing_service import get_price


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_active_batch(db: Session, plot_id: UUID) -> CropBatch | None:
    """Return the currently-active crop batch on the plot, if any."""
    return (
        db.query(CropBatch)
        .filter(
            CropBatch.plot_id == plot_id,
            CropBatch.is_active.is_(True),
        )
        .order_by(CropBatch.planted_at.desc())
        .first()
    )


def _lookup_price(
    db: Session,
    *,
    ingredient: str | None = None,
    category: InputCategory | None = None,
    tenant_id: UUID | None = None,
) -> InputPrice | None:
    """Wrapper around get_price that handles missing args gracefully."""
    return get_price(
        db,
        active_ingredient=ingredient,
        category=category,
        tenant_id=tenant_id,
    )


def _post_entry(
    db: Session,
    *,
    task: Task,
    plot: Plot,
    category: LedgerCategory,
    qty: Decimal,
    unit: str,
    input_price: InputPrice,
    details: dict | None = None,
    notes: str | None = None,
) -> FinancialLedger:
    """Create and stage a single ledger entry."""
    unit_price = Decimal(str(input_price.price_lkr))
    amount = (qty * unit_price).quantize(Decimal("0.01"))

    entry = FinancialLedger(
        tenant_id=task.tenant_id,
        plot_id=plot.id,
        batch_id=_find_active_batch(db, plot.id).id if _find_active_batch(db, plot.id) else None,
        source_task_id=task.id,
        category=category,
        qty=float(qty),
        unit=unit,
        unit_price_lkr=float(unit_price),
        amount_lkr=float(amount),
        input_price_id=input_price.id,
        details=details or {},
        notes=notes,
        occurred_at=task.completed_at or datetime.now(timezone.utc),
    )
    db.add(entry)
    return entry


# ---------------------------------------------------------------------------
# Cost calculators — one per tool type
# ---------------------------------------------------------------------------

def _post_irrigation_costs(db: Session, task: Task, plot: Plot) -> list[FinancialLedger]:
    """
    Post WATER + ENERGY + LABOR entries for a control_irrigation task.

    Assumptions (from agricultural_constants):
      water_L    = duration_min × DEFAULT_DRIP_FLOW_L_PER_MIN
      energy_kWh = DEFAULT_PUMP_KW × (duration_min / 60)
      labor_hr   = DEFAULT_IRRIGATION_LABOR_HOURS
    """
    duration = Decimal(str(task.args.get("duration_min", 0)))
    if duration <= 0:
        log.info(f"Task {task.id}: irrigation duration 0; no ledger entries")
        return []

    entries: list[FinancialLedger] = []

    # --- Water ---
    water_L = duration * const.DEFAULT_DRIP_FLOW_L_PER_MIN
    water_price = _lookup_price(db, ingredient="water", tenant_id=task.tenant_id)
    if water_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.WATER,
            qty=water_L, unit="L",
            input_price=water_price,
            details={"duration_min": float(duration)},
        ))
    else:
        log.warning(f"Task {task.id}: no water price configured")

    # --- Energy ---
    energy_kwh = const.DEFAULT_PUMP_KW * (duration / Decimal("60"))
    energy_price = _lookup_price(db, ingredient="ceb_industrial", tenant_id=task.tenant_id)
    if energy_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.ENERGY,
            qty=energy_kwh.quantize(Decimal("0.001")), unit="kWh",
            input_price=energy_price,
            details={"duration_min": float(duration), "assumed_kw": float(const.DEFAULT_PUMP_KW)},
        ))

    # --- Labor (supervision) ---
    labor_price = _lookup_price(db, ingredient="farm_labor_general", tenant_id=task.tenant_id)
    if labor_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.LABOR,
            qty=const.DEFAULT_IRRIGATION_LABOR_HOURS, unit="hr",
            input_price=labor_price,
            details={"role": "irrigation_supervision"},
        ))

    return entries


def _post_spray_costs(db: Session, task: Task, plot: Plot) -> list[FinancialLedger]:
    """
    Post CHEMICAL + WATER + LABOR entries for a spray_chemical task.

    Assumptions:
      chemical_kg = (dose_ml_per_ha × area_ha) / 1000
      carrier_L   = DEFAULT_SPRAY_CARRIER_L_PER_HA × area_ha
      labor_hr    = DEFAULT_SPRAY_LABOR_HOURS_PER_HA × area_ha
    """
    dose = Decimal(str(task.args.get("dose_ml_per_ha", 0)))
    if dose <= 0:
        log.info(f"Task {task.id}: spray dose 0; no ledger entries")
        return []

    area_ha = Decimal(str(plot.area_ha or 0))
    if area_ha <= 0:
        log.warning(f"Task {task.id}: plot has no area; using 0.1 ha fallback")
        area_ha = Decimal("0.1")

    # Which chemical? Pull from args, fall back to a default.
    ingredient = task.args.get("active_ingredient") or const.DEFAULT_SPRAY_INGREDIENT

    entries: list[FinancialLedger] = []

    # --- Chemical ---
    chemical_kg = (dose * area_ha) / Decimal("1000")   # ml → kg (1 ml ≈ 1 g for liquids)
    chem_price = _lookup_price(db, ingredient=ingredient, tenant_id=task.tenant_id)
    if chem_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.CHEMICAL,
            qty=chemical_kg.quantize(Decimal("0.0001")), unit=chem_price.unit,
            input_price=chem_price,
            details={
                "dose_ml_per_ha": float(dose),
                "area_ha": float(area_ha),
                "active_ingredient": ingredient,
            },
        ))
    else:
        log.warning(f"Task {task.id}: no price for spray ingredient {ingredient!r}")

    # --- Water (carrier) ---
    carrier_L = const.DEFAULT_SPRAY_CARRIER_L_PER_HA * area_ha
    water_price = _lookup_price(db, ingredient="water", tenant_id=task.tenant_id)
    if water_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.WATER,
            qty=carrier_L.quantize(Decimal("0.1")), unit="L",
            input_price=water_price,
            details={"purpose": "spray_carrier"},
        ))

    # --- Labor ---
    labor_hr = const.DEFAULT_SPRAY_LABOR_HOURS_PER_HA * area_ha
    labor_price = _lookup_price(db, ingredient="farm_labor_general", tenant_id=task.tenant_id)
    if labor_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.LABOR,
            qty=labor_hr.quantize(Decimal("0.01")), unit="hr",
            input_price=labor_price,
            details={"role": "spray_application"},
        ))

    return entries


def _post_fertigation_costs(db: Session, task: Task, plot: Plot) -> list[FinancialLedger]:
    """
    Post WATER + FERTILIZER + ENERGY entries for a schedule_fertigation task.

    Assumptions:
      water_L       = duration_min × DEFAULT_DRIP_FLOW_L_PER_MIN
      fertilizer_kg = (water_L / 1000) × ec_target × FERTILIZER_KG_PER_1000L_AT_EC_1
    """
    duration = Decimal(str(task.args.get("duration_min", 0)))
    ec_target = Decimal(str(task.args.get("ec_target", 0)))
    if duration <= 0 or ec_target <= 0:
        log.info(f"Task {task.id}: fertigation missing duration/EC; no entries")
        return []

    entries: list[FinancialLedger] = []

    # --- Water ---
    water_L = duration * const.DEFAULT_DRIP_FLOW_L_PER_MIN
    water_price = _lookup_price(db, ingredient="water", tenant_id=task.tenant_id)
    if water_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.WATER,
            qty=water_L, unit="L",
            input_price=water_price,
            details={"duration_min": float(duration), "purpose": "fertigation_carrier"},
        ))

    # --- Fertilizer ---
    fertilizer_kg = (
        (water_L / Decimal("1000"))
        * ec_target
        * const.FERTILIZER_KG_PER_1000L_AT_EC_1
    )
    ingredient = task.args.get("fertilizer") or const.DEFAULT_FERTILIZER_INGREDIENT
    fert_price = _lookup_price(db, ingredient=ingredient, tenant_id=task.tenant_id)
    if fert_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.FERTILIZER,
            qty=fertilizer_kg.quantize(Decimal("0.001")), unit=fert_price.unit,
            input_price=fert_price,
            details={"ec_target": float(ec_target), "product": ingredient},
        ))

    # --- Energy ---
    energy_kwh = const.DEFAULT_PUMP_KW * (duration / Decimal("60"))
    energy_price = _lookup_price(db, ingredient="ceb_industrial", tenant_id=task.tenant_id)
    if energy_price:
        entries.append(_post_entry(
            db, task=task, plot=plot,
            category=LedgerCategory.ENERGY,
            qty=energy_kwh.quantize(Decimal("0.001")), unit="kWh",
            input_price=energy_price,
            details={"duration_min": float(duration)},
        ))

    return entries


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_POSTERS = {
    "control_irrigation": _post_irrigation_costs,
    "spray_chemical": _post_spray_costs,
    "schedule_fertigation": _post_fertigation_costs,
}


def post_task_costs(db: Session, task: Task) -> list[FinancialLedger]:
    """
    Post ledger entries for a completed task. Best-effort: never raises.

    Returns the list of entries that were added (uncommitted).
    Caller is responsible for db.commit().
    """
    poster = _POSTERS.get(task.tool)
    if poster is None:
        log.info(f"Task {task.id}: no cost poster for tool {task.tool!r}")
        return []

    plot = db.get(Plot, task.plot_id)
    if plot is None:
        log.warning(f"Task {task.id}: plot {task.plot_id} not found; skipping costs")
        return []

    try:
        entries = poster(db, task, plot)
        if entries:
            log.info(
                f"Task {task.id}: staged {len(entries)} ledger entries "
                f"totaling {sum(float(e.amount_lkr) for e in entries):.2f} LKR"
            )
        return entries
    except Exception as e:
        log.exception(
            f"Task {task.id}: ledger posting failed ({type(e).__name__}: {e})"
        )
        return []


# ---------------------------------------------------------------------------
# Aggregation queries
# ---------------------------------------------------------------------------

def get_batch_cost(db: Session, batch_id: UUID) -> dict:
    """Total cost breakdown for a crop batch, grouped by category."""
    from sqlalchemy import func

    rows = (
        db.query(
            FinancialLedger.category,
            func.sum(FinancialLedger.amount_lkr).label("total"),
            func.count(FinancialLedger.id).label("entries"),
        )
        .filter(FinancialLedger.batch_id == batch_id)
        .group_by(FinancialLedger.category)
        .all()
    )
    breakdown = {r.category.value: float(r.total or 0) for r in rows}
    total = sum(breakdown.values())
    entry_count = sum(r.entries for r in rows) if rows else 0
    return {
        "batch_id": str(batch_id),
        "total_lkr": total,
        "entry_count": entry_count,
        "breakdown": breakdown,
    }


def get_plot_cost(db: Session, plot_id: UUID, since: datetime | None = None) -> dict:
    """Total cost for a plot, optionally since a date."""
    from sqlalchemy import func

    q = db.query(
        FinancialLedger.category,
        func.sum(FinancialLedger.amount_lkr).label("total"),
    ).filter(FinancialLedger.plot_id == plot_id)
    if since is not None:
        q = q.filter(FinancialLedger.occurred_at >= since)

    rows = q.group_by(FinancialLedger.category).all()
    breakdown = {r.category.value: float(r.total or 0) for r in rows}
    return {
        "plot_id": str(plot_id),
        "total_lkr": sum(breakdown.values()),
        "breakdown": breakdown,
    }