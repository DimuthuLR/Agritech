"""
Safety limits matrix — hardcoded, code-reviewed, version-controlled.

    ⚠️  VALIDATION REQUIRED BEFORE PRODUCTION USE  ⚠️

Values below are STARTER estimates based on general horticultural
literature and greenhouse best practice. Before this system controls
real hardware on real Sri Lankan farms, every value MUST be validated
against:

    - Sri Lanka Department of Agriculture crop recommendations
    - Registrar of Pesticides approved product list (for chemicals)
    - Local agricultural extension officer guidance
    - On-farm measurements during your pilot phase

Each entry has a # TODO: cite marker where validation is needed.

Design:
  BASE_LIMITS      keyed by (crop, stage, region) — no soil dimension
  SOIL_MODIFIERS   multiplies water-related fields for a given soil type
  get_limits()     combines base + modifier into a fully-resolved Limits

Why this structure:
  - 8 crops × 5 stages = 40 base entries, not 40 × 9 soils = 360
  - Adding a new soil type = one line in SOIL_MODIFIERS
  - Adding a new crop = five lines in BASE_LIMITS
  - Fail closed: unknown (crop, stage, region) or unknown soil → None

Scope:
  This platform targets poly-tunnel/greenhouse and open-field drip
  horticulture in Sri Lanka. NOT paddy (flooded rice). Paddy uses a
  completely different water management model (standing water, not drip)
  and is intentionally out of scope.
"""
from dataclasses import dataclass

from app.core.safety.context import Region, SoilType, GrowthStage


# ---------------------------------------------------------------------------
# Crop catalogue — Sri Lankan horticulture (poly-tunnel + open-field drip)
# ---------------------------------------------------------------------------

CROPS = {
    "tomato",        # #1 poly-tunnel crop in SL
    "chili",         # high value, dry-zone + greenhouse
    "bell_pepper",   # capsicum — greenhouse
    "cucumber",      # greenhouse standard
    "lettuce",       # short-cycle, high turnover
    "cabbage",       # field, both zones
    "carrot",        # hill country + dry zone
    "brinjal",       # eggplant — field + greenhouse
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Limits:
    """
    Safe operating bounds for a (crop, stage, region) combination,
    BEFORE soil-specific modifiers are applied.

    Units:
      max_minutes_per_event:     minutes, single irrigation/fertigation event
      min_minutes_between:       minimum gap between consecutive events
      max_events_per_day:        maximum number of events in any rolling 24h
      max_daily_L_per_ha:        cumulative liters per hectare per day
      max_fertigation_ec:        mS/cm electrical conductivity (nutrient strength)
      max_chem_dose_ml_per_ha:   single chemical application dose
      max_chem_apps_per_week:    chemical applications per rolling 7 days
    """
    max_minutes_per_event: int
    min_minutes_between: int
    max_events_per_day: int
    max_daily_L_per_ha: float
    max_fertigation_ec: float
    max_chem_dose_ml_per_ha: float
    max_chem_apps_per_week: int
    target_soil_moisture_min: float = 0.30    # below this → irrigate
    target_soil_moisture_max: float = 0.50    # above this → don't irrigate
    notes: str = ""

    def apply_soil(self, modifier: "SoilModifier") -> "Limits":
        """Return a new Limits with soil modifiers applied to water fields."""
        return Limits(
            max_minutes_per_event=max(
                1, round(self.max_minutes_per_event * modifier.minutes_multiplier)
            ),
            min_minutes_between=max(
                1, round(self.min_minutes_between * modifier.gap_multiplier)
            ),
            max_events_per_day=max(
                1, round(self.max_events_per_day * modifier.events_multiplier)
            ),
            max_daily_L_per_ha=round(
                self.max_daily_L_per_ha * modifier.daily_multiplier, 1
            ),
            max_fertigation_ec=self.max_fertigation_ec,
            max_chem_dose_ml_per_ha=self.max_chem_dose_ml_per_ha,
            max_chem_apps_per_week=self.max_chem_apps_per_week,
            target_soil_moisture_min=self.target_soil_moisture_min,
            target_soil_moisture_max=self.target_soil_moisture_max,
            notes=self.notes,
        )

@dataclass(frozen=True)
class SoilModifier:
    """
    Adjusts water-related limits for a given soil or growing medium.
    Multipliers are relative to a "reference loam soil" (1.0).

    Sandy soils: shorter events, more frequent, less water per event.
    Clay soils:  longer events, less frequent, more water per event.
    """
    minutes_multiplier: float = 1.0
    gap_multiplier: float = 1.0
    events_multiplier: float = 1.0
    daily_multiplier: float = 1.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Soil modifiers
# ---------------------------------------------------------------------------

SOIL_MODIFIERS: dict[SoilType, SoilModifier] = {
    # --- Reference loam ---
    SoilType.REDDISH_BROWN_EARTH: SoilModifier(
        notes="Dry-zone loam. Reference profile (1.0 multipliers).",
    ),
    SoilType.RED_YELLOW_PODZOLIC: SoilModifier(
        notes="Wet-zone loam. Reference profile.",
    ),
    SoilType.IMMATURE_BROWN_LOAM: SoilModifier(
        notes="Hill-country loam. Reference profile.",
    ),

    # --- Sandy / low retention ---
    SoilType.REGOSOLS: SoilModifier(
        minutes_multiplier=0.5,
        gap_multiplier=0.6,
        events_multiplier=1.8,
        daily_multiplier=0.85,
        notes="Coastal sand. Low water-holding; irrigate lightly and often.",
    ),
    SoilType.COCO_PEAT: SoilModifier(
        minutes_multiplier=0.5,
        gap_multiplier=0.5,
        events_multiplier=2.0,
        daily_multiplier=0.75,
        notes="Coco peat substrate. Very low retention; classic pulse profile. "
              "Fertigate lightly and often; EC rises quickly in the root zone.",
    ),

    # --- Prepared mixes ---
    SoilType.SOIL_BASED_MIX: SoilModifier(
        notes="Field soil + amendments. Behaves close to loam.",
    ),
    SoilType.COMPOST_MIX: SoilModifier(
        minutes_multiplier=0.8,
        gap_multiplier=0.9,
        events_multiplier=1.2,
        daily_multiplier=0.9,
        notes="Compost-heavy mix. Good retention but drains freely; slightly "
              "more frequent than loam.",
    ),

    # --- Clay / high retention ---
    SoilType.LOW_HUMIC_GLEY: SoilModifier(
        minutes_multiplier=1.5,
        gap_multiplier=1.5,
        events_multiplier=0.6,
        daily_multiplier=1.2,
        notes="Lowland clay. Poor drainage; avoid waterlogging. "
              "Longer intervals, larger events.",
    ),

    # --- Unknown ---
    SoilType.OTHER: SoilModifier(
        notes="Soil type unknown. System uses reference-loam profile. "
              "Recommend reclassifying the plot for accurate irrigation.",
    ),
}


# ---------------------------------------------------------------------------
# Base limits — keyed by (crop, stage, region)
# ---------------------------------------------------------------------------
#
# Reference values assume REDDISH_BROWN_EARTH (loam). Soil modifiers adjust.
# Region currently only LK; others will return None → fail closed.

BASE_LIMITS: dict[tuple[str, GrowthStage, Region], Limits] = {

    # =====================================================================
    # TOMATO
    # =====================================================================
    # #1 poly-tunnel crop. Sensitive to waterlogging (root disease) and to
    # inconsistent moisture (blossom-end rot). Peak demand at flowering
    # and fruit sizing.
    # TODO: cite DoA Horticultural Research and Development Institute

    ("tomato", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=60, max_events_per_day=4,
        max_daily_L_per_ha=18_000, max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=300, max_chem_apps_per_week=1,
        notes="Light frequent watering. Keep foliage dry (blight risk).",
    ),
    ("tomato", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=32_000, max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=800, max_chem_apps_per_week=2,
        notes="Increasing demand. Drip preferred to reduce foliar disease.",
    ),
    ("tomato", GrowthStage.FLOWERING, Region.LK): Limits(
        max_minutes_per_event=15, min_minutes_between=45, max_events_per_day=8,
        max_daily_L_per_ha=45_000, max_fertigation_ec=2.5,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Peak. Consistent moisture critical — irregular causes blossom-end rot. "
              "Avoid overhead irrigation during flowering.",
    ),
    ("tomato", GrowthStage.FRUITING, Region.LK): Limits(
        max_minutes_per_event=15, min_minutes_between=45, max_events_per_day=8,
        max_daily_L_per_ha=50_000, max_fertigation_ec=2.8,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Fruit sizing. Reduce late to concentrate flavour.",
    ),
    ("tomato", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=120, max_events_per_day=3,
        max_daily_L_per_ha=20_000, max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Ripening. Reduce water. No chemicals in harvest window.",
    ),

    # =====================================================================
    # CHILI (green chili)
    # =====================================================================
    # High-value cash crop. Sensitive to both drought (flower drop) and
    # waterlogging (root rot). Well-drained soil essential.
    # TODO: cite DoA Field Crops Research and Development Institute

    ("chili", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=60, max_events_per_day=4,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=300, max_chem_apps_per_week=1,
        notes="Very light. Seedlings prone to damping-off if overwatered.",
    ),
    ("chili", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=10, min_minutes_between=60, max_events_per_day=5,
        max_daily_L_per_ha=25_000, max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=800, max_chem_apps_per_week=2,
        notes="Moderate demand. Well-drained soil essential.",
    ),
    ("chili", GrowthStage.FLOWERING, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=35_000, max_fertigation_ec=2.2,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Peak. Avoid water stress — flower drop risk.",
    ),
    ("chili", GrowthStage.FRUITING, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=35_000, max_fertigation_ec=2.5,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Steady moisture — irregular = fruit cracking.",
    ),
    ("chili", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=120, max_events_per_day=3,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Reduce water as fruit ripens.",
    ),

    # =====================================================================
    # BELL PEPPER (capsicum)
    # =====================================================================
    # Similar to chili but grown almost exclusively in protected culture.
    # TODO: cite DoA — largely follows chili recommendations

    ("bell_pepper", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=60, max_events_per_day=4,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=300, max_chem_apps_per_week=1,
        notes="Light frequent. Protect from damping-off.",
    ),
    ("bell_pepper", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=10, min_minutes_between=60, max_events_per_day=5,
        max_daily_L_per_ha=25_000, max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=800, max_chem_apps_per_week=2,
        notes="Moderate demand.",
    ),
    ("bell_pepper", GrowthStage.FLOWERING, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=35_000, max_fertigation_ec=2.2,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Peak. Flower drop risk if stressed.",
    ),
    ("bell_pepper", GrowthStage.FRUITING, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=35_000, max_fertigation_ec=2.5,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Steady moisture for fruit set.",
    ),
    ("bell_pepper", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=120, max_events_per_day=3,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Reduce water during colour change.",
    ),

    # =====================================================================
    # CUCUMBER
    # =====================================================================
    # High water demand. Grown on trellis in poly-tunnels.
    # TODO: cite DoA Horticultural Research recommendations

    ("cucumber", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=6, min_minutes_between=60, max_events_per_day=4,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=300, max_chem_apps_per_week=1,
        notes="Small volumes. Do not overwater early.",
    ),
    ("cucumber", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=10, min_minutes_between=45, max_events_per_day=6,
        max_daily_L_per_ha=30_000, max_fertigation_ec=2.2,
        max_chem_dose_ml_per_ha=800, max_chem_apps_per_week=2,
        notes="Fast growth. Steady moisture.",
    ),
    ("cucumber", GrowthStage.FLOWERING, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=45, max_events_per_day=8,
        max_daily_L_per_ha=45_000, max_fertigation_ec=2.5,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Peak. Cucumbers abort fruit if stressed.",
    ),
    ("cucumber", GrowthStage.FRUITING, Region.LK): Limits(
        max_minutes_per_event=15, min_minutes_between=45, max_events_per_day=8,
        max_daily_L_per_ha=50_000, max_fertigation_ec=2.8,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Peak. Consistent moisture for straight, bitter-free fruit.",
    ),
    ("cucumber", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=10, min_minutes_between=90, max_events_per_day=4,
        max_daily_L_per_ha=25_000, max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Taper water near harvest.",
    ),

    # =====================================================================
    # LETTUCE
    # =====================================================================
    # Short cycle (30-45 days), high turnover, steady low-volume demand.
    # TODO: cite DoA / commercial lettuce production guides

    ("lettuce", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=4, min_minutes_between=60, max_events_per_day=4,
        max_daily_L_per_ha=10_000, max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=200, max_chem_apps_per_week=1,
        notes="Very small volumes. Avoid wetting leaf.",
    ),
    ("lettuce", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=6, min_minutes_between=45, max_events_per_day=6,
        max_daily_L_per_ha=20_000, max_fertigation_ec=1.8,
        max_chem_dose_ml_per_ha=500, max_chem_apps_per_week=1,
        notes="Steady moisture for even growth.",
    ),
    ("lettuce", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=6, min_minutes_between=60, max_events_per_day=5,
        max_daily_L_per_ha=20_000, max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Heading stage. No chemicals near harvest.",
    ),

    # =====================================================================
    # CABBAGE
    # =====================================================================
    # Field crop, wide climatic range. Moderate water demand.
    # TODO: cite DoA Vegetable recommendations

    ("cabbage", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=6, min_minutes_between=60, max_events_per_day=4,
        max_daily_L_per_ha=12_000, max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=300, max_chem_apps_per_week=1,
        notes="Small volumes. Guard against damping-off.",
    ),
    ("cabbage", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=10, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=25_000, max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=800, max_chem_apps_per_week=2,
        notes="Foliar development. Steady moisture.",
    ),
    ("cabbage", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=10, min_minutes_between=60, max_events_per_day=5,
        max_daily_L_per_ha=25_000, max_fertigation_ec=1.8,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Head formation. Reduce water in final week.",
    ),

    # =====================================================================
    # CARROT
    # =====================================================================
    # Root crop. Overwatering causes forking and rot. Deeper, less frequent.
    # TODO: cite DoA Root Crop recommendations

    ("carrot", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=6, min_minutes_between=90, max_events_per_day=3,
        max_daily_L_per_ha=10_000, max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=200, max_chem_apps_per_week=1,
        notes="Light but even moisture for germination.",
    ),
    ("carrot", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=90, max_events_per_day=4,
        max_daily_L_per_ha=20_000, max_fertigation_ec=1.8,
        max_chem_dose_ml_per_ha=500, max_chem_apps_per_week=1,
        notes="Deep, less frequent watering encourages downward root growth.",
    ),
    ("carrot", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=6, min_minutes_between=120, max_events_per_day=3,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Taper water near harvest. Overwatering causes splitting.",
    ),

    # =====================================================================
    # BRINJAL (eggplant / aubergine)
    # =====================================================================
    # Robust crop. Similar water needs to chili.
    # TODO: cite DoA recommendations

    ("brinjal", GrowthStage.SEEDLING, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=60, max_events_per_day=4,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=300, max_chem_apps_per_week=1,
        notes="Light and frequent.",
    ),
    ("brinjal", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_minutes_per_event=10, min_minutes_between=60, max_events_per_day=5,
        max_daily_L_per_ha=25_000, max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=800, max_chem_apps_per_week=2,
        notes="Moderate. Deep root system tolerates mild dry-down.",
    ),
    ("brinjal", GrowthStage.FLOWERING, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=35_000, max_fertigation_ec=2.2,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Peak. Adequate water for fruit set.",
    ),
    ("brinjal", GrowthStage.FRUITING, Region.LK): Limits(
        max_minutes_per_event=12, min_minutes_between=60, max_events_per_day=6,
        max_daily_L_per_ha=35_000, max_fertigation_ec=2.5,
        max_chem_dose_ml_per_ha=1000, max_chem_apps_per_week=2,
        notes="Steady moisture.",
    ),
    ("brinjal", GrowthStage.MATURITY, Region.LK): Limits(
        max_minutes_per_event=8, min_minutes_between=120, max_events_per_day=3,
        max_daily_L_per_ha=15_000, max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0, max_chem_apps_per_week=0,
        notes="Reduce water before final harvest.",
    ),
}


# ---------------------------------------------------------------------------
# Crop alias normalisation
# ---------------------------------------------------------------------------

_CROP_ALIASES = {
    "capsicum": "bell_pepper",
    "pepper": "bell_pepper",
    "sweet_pepper": "bell_pepper",
    "green_chili": "chili",
    "green_chilli": "chili",
    "chilli": "chili",
    "eggplant": "brinjal",
    "aubergine": "brinjal",
    "cucumbers": "cucumber",
}


def normalise_crop(crop: str) -> str:
    """Normalise a user-supplied crop string to a canonical key."""
    key = crop.strip().lower().replace(" ", "_")
    return _CROP_ALIASES.get(key, key)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def get_limits(
    crop: str,
    stage: GrowthStage,
    soil_type: SoilType,
    region: Region,
) -> Limits | None:
    """
    Return fully-resolved limits (base + soil modifiers applied).
    Returns None if the crop/stage/region combination isn't configured,
    or if the soil type has no modifier entry.

    The gate MUST fail closed on None.
    """
    canonical = normalise_crop(crop)
    base = BASE_LIMITS.get((canonical, stage, region))
    if base is None:
        return None

    modifier = SOIL_MODIFIERS.get(soil_type)
    if modifier is None:
        return None

    return base.apply_soil(modifier)


def is_supported(crop: str, stage: GrowthStage, soil_type: SoilType, region: Region) -> bool:
    """Cheap check — does this combination have limits configured?"""
    return get_limits(crop, stage, soil_type, region) is not None