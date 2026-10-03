"""
SafetyContext — the immutable snapshot of world state for a safety decision.

Every call to validate_tool_call() takes one of these. The context records
everything the gate needs to know: what crop, what stage, what weather,
what recent history. Once constructed, it cannot change. If a decision
is made against a context, we can reproduce that decision exactly,
which is essential for audit and for post-mortem analysis.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID


class Region(str, Enum):
    """
    Agricultural regions. Sri Lanka is the primary region for this platform.
    Sub-national zones may be added later for finer-grained rules.
    """
    LK = "LK"       # Sri Lanka — primary
    IN = "IN"       # India
    EU = "EU"       # European Union (generic)
    US = "US"       # United States (generic)
    OTHER = "OTHER"

class SoilType(str, Enum):
    """
    Soil type or growing medium. Set by the user at plot creation.

    Natural soils use Sri Lanka Department of Agriculture classification.
    Growing media are the common substrates for poly-tunnel/greenhouse work.
    """
    # Natural soils (Sri Lanka)
    RED_YELLOW_PODZOLIC = "red_yellow_podzolic"      # wet zone, tea/rubber country
    REDDISH_BROWN_EARTH = "reddish_brown_earth"      # dry zone, most vegetable cultivation
    LOW_HUMIC_GLEY = "low_humic_gley"                # lowland, poor drainage
    REGOSOLS = "regosols"                            # coastal sands, coconut triangle
    IMMATURE_BROWN_LOAM = "immature_brown_loam"      # hill country, Nuwara Eliya

    # Growing media (poly-tunnel / greenhouse)
    COCO_PEAT = "coco_peat"                          # very common in Sri Lanka
    SOIL_BASED_MIX = "soil_based_mix"                # field soil + amendments
    COMPOST_MIX = "compost_mix"

    # Fallback
    OTHER = "other"                                  # unknown; system uses conservative defaults

class GrowthStage(str, Enum):
    """
    Generic growth stages. These map to specific crop calendars later.
    For Sri Lankan paddy: SEEDLING → TILLERING → VEG (booting) → FLOWER → FRUIT (grain fill)
    For Sri Lankan tomato: SEEDLING → VEG → FLOWER → FRUIT
    """
    SEEDLING = "seedling"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    MATURITY = "maturity"
    HARVEST = "harvest"
    FALLOW = "fallow"


@dataclass(frozen=True)
class WeatherSnapshot:
    """
    Weather conditions and near-term forecast for a plot's location.
    All values are from the moment of the snapshot; the forecast fields
    are for the next 6 hours.
    """
    # Current conditions
    temp_c: float
    humidity: float              # 0.0–1.0
    wind_kmh: float

    # Forecast — next 6 hours
    rain_forecast_mm_6h: float   # cumulative expected rainfall

    # When this was fetched (used to detect stale weather data)
    fetched_at: datetime

    # Source: 'open-meteo', 'manual', 'test'
    source: str = "manual"

    def is_stale(self, max_age_minutes: int = 30) -> bool:
        """Returns True if the snapshot is older than max_age_minutes."""
        age = datetime.now(timezone.utc) - self.fetched_at
        return age.total_seconds() > max_age_minutes * 60


@dataclass(frozen=True)
class SensorSnapshot:
    """
    Latest sensor readings for a plot, at the moment of the decision.
    """
    soil_moisture: float | None = None     # 0.0–1.0 volumetric
    temperature: float | None = None        # °C
    humidity: float | None = None           # 0.0–1.0
    ph: float | None = None
    ec: float | None = None                 # mS/cm

    # Seconds since the newest reading in this snapshot
    newest_reading_age_s: float = 0.0

    def is_stale(self, max_age_seconds: float = 1800) -> bool:
        """Default: stale if newest reading is older than 30 minutes."""
        return self.newest_reading_age_s > max_age_seconds


@dataclass(frozen=True)
class SafetyContext:
    """
    Complete immutable state for a safety decision on a plot.

    Constructed fresh for every validate_tool_call(). Fields capture
    everything the gate needs; nothing is queried lazily.
    """
    # Identity
    plot_id: UUID
    tenant_id: UUID

    # Agronomy
    # Agronomy
    crop: str                   # e.g. 'tomato', 'chili', 'cabbage'
    stage: GrowthStage
    soil_type: SoilType         # set by the user at plot creation
    region: Region

    # Weather (may be stale — always check .is_stale() if it matters)
    weather: WeatherSnapshot

    # Sensors (may be stale — see SensorSnapshot.is_stale())
    sensors: SensorSnapshot

    # Recent operational history
    last_irrigation_at: datetime | None = None
    volume_today_L: float = 0.0
    volume_today_per_ha_L: float = 0.0
    irrigation_events_today: int = 0     # for pulse limit checking

    # Snapshot time — when the context was built
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # --- Convenience predicates ---

    @property
    def is_raining_soon(self) -> bool:
        return self.weather.rain_forecast_mm_6h >= 5.0

    @property
    def is_windy(self) -> bool:
        return self.weather.wind_kmh >= 30.0

    @property
    def is_hot(self) -> bool:
        return self.weather.temp_c >= 32.0

    @property
    def has_recent_irrigation(self) -> bool:
        """True if irrigated in the last 2 hours."""
        if self.last_irrigation_at is None:
            return False
        age = datetime.now(timezone.utc) - self.last_irrigation_at
        return age.total_seconds() < 7200

    @property
    def minutes_since_last_irrigation(self) -> float | None:
        """Minutes since last irrigation, or None if never irrigated."""
        if self.last_irrigation_at is None:
            return None
        delta = datetime.now(timezone.utc) - self.last_irrigation_at
        return delta.total_seconds() / 60.0

    def __repr__(self) -> str:
        return (
            f"<SafetyContext plot={self.plot_id} crop={self.crop!r} "
            f"stage={self.stage.value} region={self.region.value} "
            f"rain6h={self.weather.rain_forecast_mm_6h}mm "
            f"wind={self.weather.wind_kmh}km/h>"
        )