"""
Agricultural constants — assumptions used in cost calculations.

These are DEFAULTS. In production, they should become plot-level
attributes (each plot's pump spec, drip flow rate, etc.). For now,
they're global constants tuned for typical Sri Lankan smallholder
and poly-tunnel operations.

    ⚠️  Every value here affects cost calculations. Verify against
    actual equipment specs before relying on ledger numbers.
"""
from decimal import Decimal


# ---- Irrigation ----
# Typical drip irrigation flow rate for a small plot.
# 20 L/min = 1.2 m³/hr. Higher for sprinklers, lower for micro-drip.
DEFAULT_DRIP_FLOW_L_PER_MIN = Decimal("20.0")

# Pump power draw while irrigating.
# 0.5 kW is typical for a 1-2 HP surface pump serving a small plot.
DEFAULT_PUMP_KW = Decimal("0.5")


# ---- Spraying ----
# Foliar spray carrier volume — liters of water carrier per hectare.
# 500 L/ha is a common medium-volume spray for horticulture.
DEFAULT_SPRAY_CARRIER_L_PER_HA = Decimal("500.0")

# Labor time to perform a spray application (hours per hectare).
# Includes mixing, walking, cleaning. 0.5 hr/ha for a small plot.
DEFAULT_SPRAY_LABOR_HOURS_PER_HA = Decimal("0.5")

# Default chemical when the task doesn't specify one.
# Copper oxychloride is the most common broad-spectrum fungicide.
DEFAULT_SPRAY_INGREDIENT = "copper_oxychloride"


# ---- Fertigation ----
# Fertilizer mass per 1000 L of irrigation water at EC target of 1.0.
# Rough approximation; refined by crop/stage in later phases.
FERTILIZER_KG_PER_1000L_AT_EC_1 = Decimal("0.5")

# Default fertilizer product when task doesn't specify one.
DEFAULT_FERTILIZER_INGREDIENT = "npk_15_15_15"


# ---- Labor ----
# Labor hours to supervise an irrigation event (setup + check).
DEFAULT_IRRIGATION_LABOR_HOURS = Decimal("0.1")