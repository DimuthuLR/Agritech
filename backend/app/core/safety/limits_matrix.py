"""
Safety limits matrix — hardcoded, code-reviewed, version-controlled.

Every actuator action the AI proposes must fit within these limits.
If a (crop, stage, region) combination isn't configured, the gate
FAILS CLOSED — refuses the action. There are no default limits.

    ⚠️ VALIDATION REQUIRED BEFORE PRODUCTION USE ⚠️

The numeric values below are STARTER VALUES based on general agronomic
literature. Before this system controls real hardware on a real farm,
every limit MUST be validated against:

  - Sri Lanka Department of Agriculture crop recommendations
  - Registrar of Pesticides approved product list
  - Local extension officer guidance for the specific district

Each line is marked with a citation TODO where validation is needed.

Changing any value here is a deliberate code change that goes through
git review. There is no runtime override, no admin UI to edit these.
That's intentional — safety limits should not be editable at 3 AM.
"""
from dataclasses import dataclass

from app.core.safety.context import Region, GrowthStage


# ---------------------------------------------------------------------------
# Crop catalogue (Sri Lanka primary)
# ---------------------------------------------------------------------------

# Free-form strings for now; the DB stores crop as a string.
# When this grows past ~20 crops, convert to an enum and add a proper registry.

CROPS_SRI_LANKA = {
    "paddy",        # rice — Oryza sativa, the dominant crop
    "tomato",       # Solanum lycopersicum
    "chili",        # Capsicum spp. (green chili, mostly)
    "brinjal",      # eggplant / aubergine
    "maize",        # Zea mays (field corn, also sweet corn)
    "tea",          # Camellia sinensis — wet zone highlands
    "coconut",      # Cocos nucifera
    "rubber",       # Hevea brasiliensis
    "green_gram",   # mung bean — common rotation crop
    "cowpea",       # Vigna unguiculata
    "onion",        # big onion (red) and small onion (shallot)
    "cabbage",      # hill country vegetable
    "carrot",       # hill country vegetable
    "beetroot",
    "beans",        # common bean — upcountry
}


# ---------------------------------------------------------------------------
# Limits dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Limits:
    """
    Safe operating bounds for one (crop, stage, region) combination.

    Units:
      - max_irrigation_min:      minutes, per single irrigation event
      - max_daily_L_per_ha:      liters per hectare, cumulative per day
      - min_hours_between:       minimum gap between irrigation events
      - max_fertigation_ec:      mS/cm, electrical conductivity of nutrient solution
      - max_chem_dose_ml_per_ha: milliliters per hectare, single application
      - max_chem_apps_per_week:  number of chemical applications allowed per 7 days
      - requires_approval:       tools that must go through human approval regardless
    """
    max_irrigation_min: int
    max_daily_L_per_ha: float
    min_hours_between: float
    max_fertigation_ec: float
    max_chem_dose_ml_per_ha: float
    max_chem_apps_per_week: int

    # Crop-specific safety overrides
    # (e.g. "paddy" requires flooding depth control, "tea" is drought-sensitive)
    notes: str = ""


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------
#
# Key: (crop, stage, region)
# Value: Limits
#
# Missing keys → gate refuses. Do NOT add a "default" fallback.

LIMITS: dict[tuple[str, GrowthStage, Region], Limits] = {

    # ==========================================================
    # PADDY (rice) — Sri Lanka, all stages, LK region
    # ==========================================================
    # Paddy is grown under flooded conditions in most of Sri Lanka,
    # but Alternate Wetting and Drying (AWD) is increasingly promoted
    # by DoA for water savings.
    # TODO: validate values against DoA Rice Research and Development Institute

    ("paddy", GrowthStage.SEEDLING, Region.LK): Limits(
        max_irrigation_min=30,
        max_daily_L_per_ha=30_000,
        min_hours_between=8,
        max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=500,
        max_chem_apps_per_week=1,
        notes="Maintain 2-3 cm standing water; avoid deep flooding (tiller rot risk).",
    ),
    ("paddy", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_irrigation_min=45,
        max_daily_L_per_ha=50_000,
        min_hours_between=6,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=1000,
        max_chem_apps_per_week=2,
        notes="Peak water demand. AWD allowed — wait for 15cm drop below surface.",
    ),
    ("paddy", GrowthStage.FLOWERING, Region.LK): Limits(
        max_irrigation_min=45,
        max_daily_L_per_ha=55_000,
        min_hours_between=6,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=1000,
        max_chem_apps_per_week=2,
        notes="Critical stage — water stress = yield loss. Do not let field dry.",
    ),
    ("paddy", GrowthStage.FRUITING, Region.LK): Limits(
        max_irrigation_min=30,
        max_daily_L_per_ha=35_000,
        min_hours_between=8,
        max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=750,
        max_chem_apps_per_week=1,
        notes="Grain fill. Reduce water slightly; drain 10-14 days before harvest.",
    ),
    ("paddy", GrowthStage.MATURITY, Region.LK): Limits(
        max_irrigation_min=0,
        max_daily_L_per_ha=0,
        min_hours_between=24,
        max_fertigation_ec=0.0,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="No irrigation. Field must drain before harvest. No chemicals.",
    ),

    # ==========================================================
    # TOMATO — Sri Lanka, all stages, LK region
    # ==========================================================
    # Mostly grown in up-country (Nuwara Eliya, Badulla) and dry zone
    # with drip irrigation. Very sensitive to waterlogging and to
    # blossom-end rot from inconsistent watering.
    # TODO: validate against DoA Horticultural Research and Development Institute

    ("tomato", GrowthStage.SEEDLING, Region.LK): Limits(
        max_irrigation_min=15,
        max_daily_L_per_ha=15_000,
        min_hours_between=12,
        max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=300,
        max_chem_apps_per_week=1,
        notes="Light frequent watering. Avoid leaf wetting (blight risk).",
    ),
    ("tomato", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_irrigation_min=30,
        max_daily_L_per_ha=35_000,
        min_hours_between=8,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=800,
        max_chem_apps_per_week=2,
        notes="Increasing demand. Drip preferred to reduce foliar disease.",
    ),
    ("tomato", GrowthStage.FLOWERING, Region.LK): Limits(
        max_irrigation_min=45,
        max_daily_L_per_ha=50_000,
        min_hours_between=6,
        max_fertigation_ec=2.5,
        max_chem_dose_ml_per_ha=1000,
        max_chem_apps_per_week=2,
        notes="Peak demand. Consistent moisture critical — irregular = blossom-end rot. "
              "Avoid overhead irrigation during flowering.",
    ),
    ("tomato", GrowthStage.FRUITING, Region.LK): Limits(
        max_irrigation_min=45,
        max_daily_L_per_ha=55_000,
        min_hours_between=6,
        max_fertigation_ec=2.8,
        max_chem_dose_ml_per_ha=1000,
        max_chem_apps_per_week=2,
        notes="Peak demand during fruit sizing. Reduce before ripening to concentrate flavour.",
    ),
    ("tomato", GrowthStage.MATURITY, Region.LK): Limits(
        max_irrigation_min=20,
        max_daily_L_per_ha=20_000,
        min_hours_between=12,
        max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="Reducing water improves fruit quality. No chemicals — harvest window.",
    ),

    # ==========================================================
    # CHILI — Sri Lanka
    # ==========================================================
    # Green chili is a major cash crop, especially in dry zone (Anuradhapura,
    # Puttalam, Kurunegala). Sensitive to both drought and waterlogging.
    # TODO: validate against DoA Field Crops Research and Development Institute

    ("chili", GrowthStage.SEEDLING, Region.LK): Limits(
        max_irrigation_min=15,
        max_daily_L_per_ha=12_000,
        min_hours_between=12,
        max_fertigation_ec=1.2,
        max_chem_dose_ml_per_ha=300,
        max_chem_apps_per_week=1,
        notes="Very light. Chili seedlings are prone to damping-off if overwatered.",
    ),
    ("chili", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_irrigation_min=30,
        max_daily_L_per_ha=30_000,
        min_hours_between=8,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=800,
        max_chem_apps_per_week=2,
        notes="Moderate demand. Well-drained soil essential.",
    ),
    ("chili", GrowthStage.FLOWERING, Region.LK): Limits(
        max_irrigation_min=40,
        max_daily_L_per_ha=45_000,
        min_hours_between=8,
        max_fertigation_ec=2.2,
        max_chem_dose_ml_per_ha=1000,
        max_chem_apps_per_week=2,
        notes="Peak demand. Avoid water stress — flower drop risk.",
    ),
    ("chili", GrowthStage.FRUITING, Region.LK): Limits(
        max_irrigation_min=40,
        max_daily_L_per_ha=45_000,
        min_hours_between=8,
        max_fertigation_ec=2.5,
        max_chem_dose_ml_per_ha=1000,
        max_chem_apps_per_week=2,
        notes="Fruit development. Steady moisture — irregular = fruit cracking.",
    ),
    ("chili", GrowthStage.MATURITY, Region.LK): Limits(
        max_irrigation_min=20,
        max_daily_L_per_ha=20_000,
        min_hours_between=12,
        max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="Reduce water as fruit ripens.",
    ),

    # ==========================================================
    # TEA — Sri Lanka wet zone
    # ==========================================================
    # Mostly rainfed in the wet zone (Kandy, Nuwara Eliya, Badulla, Ratnapura).
    # Irrigation is supplemental — only in the dry zone (Uva, parts of
    # Eastern Province) or during unusual dry spells.
    # Tea cannot tolerate waterlogging at all.
    # TODO: validate against TRI (Tea Research Institute of Sri Lanka)

    ("tea", GrowthStage.SEEDLING, Region.LK): Limits(
        max_irrigation_min=20,
        max_daily_L_per_ha=15_000,
        min_hours_between=24,
        max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="Young tea. Only irrigate if extended dry spell. No chemicals on young plants.",
    ),
    ("tea", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_irrigation_min=40,
        max_daily_L_per_ha=25_000,
        min_hours_between=24,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=500,
        max_chem_apps_per_week=1,
        notes="Supplemental only. Tea is drought-tolerant but responds to irrigation in dry spells. "
              "Never waterlog — drainage is critical.",
    ),
    ("tea", GrowthStage.FLOWERING, Region.LK): Limits(
        max_irrigation_min=30,
        max_daily_L_per_ha=20_000,
        min_hours_between=24,
        max_fertigation_ec=1.5,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="Tea flowering is vegetative; 'flowering' stage here means the flush-picking window. "
              "Minimal intervention. No chemicals.",
    ),
    ("tea", GrowthStage.HARVEST, Region.LK): Limits(
        max_irrigation_min=0,
        max_daily_L_per_ha=0,
        min_hours_between=48,
        max_fertigation_ec=0.0,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="During active plucking, do not irrigate — leaf quality suffers.",
    ),

    # ==========================================================
    # COCONUT — Sri Lanka
    # ==========================================================
    # Long-cycle tree crop (60+ year productive life). Mostly rainfed
    # in the wet zone; dry zone (Puttalam, Hambantota) benefits from
    # supplemental irrigation. Chemicals are rarely needed.
    # TODO: validate against Coconut Research Institute (CRI)

    ("coconut", GrowthStage.VEGETATIVE, Region.LK): Limits(
        max_irrigation_min=60,
        max_daily_L_per_ha=40_000,
        min_hours_between=48,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="Deep, infrequent irrigation. Basin or drip. No chemicals without CRI/DoA approval.",
    ),
    ("coconut", GrowthStage.FLOWERING, Region.LK): Limits(
        max_irrigation_min=60,
        max_daily_L_per_ha=50_000,
        min_hours_between=48,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="Peak demand for nut set. Very sensitive to water stress at this stage.",
    ),
    ("coconut", GrowthStage.FRUITING, Region.LK): Limits(
        max_irrigation_min=60,
        max_daily_L_per_ha=50_000,
        min_hours_between=48,
        max_fertigation_ec=2.0,
        max_chem_dose_ml_per_ha=0,
        max_chem_apps_per_week=0,
        notes="Nut development. Maintain consistent moisture.",
    ),
}


# ---------------------------------------------------------------------------
# Crop alias normalisation
# ---------------------------------------------------------------------------

# Map common user-typed variants → canonical crop key
_CROP_ALIASES = {
    "rice": "paddy",
    "paddy_rice": "paddy",
    "eggplant": "brinjal",
    "aubergine": "brinjal",
    "green_chili": "chili",
    "green_chilli": "chili",
    "chilli": "chili",
    "mung": "green_gram",
    "mung_bean": "green_gram",
    "green_gram_bean": "green_gram",
    "corn": "maize",
    "sweet_corn": "maize",
}


def normalise_crop(crop: str) -> str:
    """Normalise a user-supplied crop string to a canonical key."""
    key = crop.strip().lower().replace(" ", "_")
    return _CROP_ALIASES.get(key, key)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def get_limits(crop: str, stage: GrowthStage, region: Region) -> Limits | None:
    """
    Look up limits for a (crop, stage, region) combination.
    Returns None if unconfigured — the gate MUST fail closed in that case.
    """
    canonical = normalise_crop(crop)
    return LIMITS.get((canonical, stage, region))


def is_supported(crop: str, stage: GrowthStage, region: Region) -> bool:
    """Cheap check — does this combination have limits configured?"""
    return get_limits(crop, stage, region) is not None