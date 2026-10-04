"""
Pricing service — lookup and calculation for input costs.

The vision model gives us an estimate (a guess). This service gives us
a real number (computed from verified prices).

Phase 8a scope: lookup by product, ingredient, or category.
Phase 8c scope: cost calculations for spray and fertigation.
"""
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.input_price import InputCategory, InputPrice


def get_price(
    db: Session,
    *,
    product_name: str | None = None,
    active_ingredient: str | None = None,
    category: InputCategory | None = None,
    tenant_id: UUID | None = None,
    region: str = "LK",
    on_date: date | None = None,
) -> InputPrice | None:
    """
    Find the applicable price for an input.

    Priority:
      1. Tenant-specific price (if tenant_id provided)
      2. Global catalog price
      3. None (no matching price configured)

    All filters must match if provided. Most specific match wins.
    """
    query_date = on_date or date.today()

    base_filters = [
        InputPrice.region == region,
        InputPrice.valid_from <= query_date,
        (InputPrice.valid_until.is_(None)) | (InputPrice.valid_until >= query_date),
    ]

    def _filtered(q, tid):
        if tid is None:
            q = q.filter(InputPrice.tenant_id.is_(None))
        else:
            q = q.filter(InputPrice.tenant_id == tid)
        if product_name is not None:
            q = q.filter(InputPrice.product_name == product_name)
        if active_ingredient is not None:
            q = q.filter(InputPrice.active_ingredient == active_ingredient)
        if category is not None:
            q = q.filter(InputPrice.category == category)
        return q

    # 1. Try tenant-specific first
    if tenant_id is not None:
        result = (
            _filtered(db.query(InputPrice), tenant_id)
            .filter(*base_filters)
            .order_by(InputPrice.valid_from.desc())
            .first()
        )
        if result is not None:
            return result

    # 2. Fall back to global
    return (
        _filtered(db.query(InputPrice), None)
        .filter(*base_filters)
        .order_by(InputPrice.valid_from.desc())
        .first()
    )