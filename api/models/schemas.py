"""Pydantic response/request models for the F1 Telemetry Oracle API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================
# Circuits
# ============================================================
class CircuitResponse(BaseModel):
    circuit_id: str
    circuit_name: str
    country: str
    locality: str | None = None
    track_length_m: float | None = None
    lat: float | None = None
    lng: float | None = None
    created_at: datetime | None = None


# ============================================================
# Drivers
# ============================================================
class DriverResponse(BaseModel):
    driver_id: str
    code: str | None = None
    first_name: str
    last_name: str
    driver_number: int | None = None
    nationality: str | None = None
    is_sim_player: bool = False
    created_at: datetime | None = None


# ============================================================
# Teams
# ============================================================
class TeamResponse(BaseModel):
    team_id: str
    team_name: str
    color_hex: str | None = None
    engine: str | None = None
    created_at: datetime | None = None


# ============================================================
# Sessions
# ============================================================
class SessionResponse(BaseModel):
    session_id: str
    circuit_id: str
    session_type: str
    source: str
    season: int | None = None
    round_number: int | None = None
    air_temp_c: float | None = None
    track_temp_c: float | None = None
    started_at: datetime | None = None
    created_at: datetime | None = None


# ============================================================
# Laps
# ============================================================
class LapResponse(BaseModel):
    lap_id: str
    session_id: str
    driver_id: str
    lap_number: int
    sector1_ms: int | None = None
    sector2_ms: int | None = None
    sector3_ms: int | None = None
    lap_time_ms: int | None = None
    tire_compound: str | None = None
    tire_age_laps: int | None = None
    fuel_load_kg: float | None = None
    ers_deploy_pct: float | None = None
    is_valid: bool = True
    position: int | None = None
    created_at: datetime | None = None


class SimilarLapResponse(BaseModel):
    lap: LapResponse
    distance: float = Field(description="Vector distance (lower = more similar)")


# ============================================================
# Telemetry Frames
# ============================================================
class TelemetryFrameResponse(BaseModel):
    frame_id: str
    lap_id: str
    timestamp_ms: int
    distance_m: float | None = None
    speed_kph: float | None = None
    throttle_pct: float | None = None
    brake_pct: float | None = None
    steering: float | None = None
    gear: int | None = None
    rpm: int | None = None
    drs: int | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    pos_z: float | None = None
    g_lat: float | None = None
    g_lon: float | None = None
    tire_temp_fl: float | None = None
    tire_temp_fr: float | None = None
    tire_temp_rl: float | None = None
    tire_temp_rr: float | None = None
    brake_temp_fl: float | None = None
    brake_temp_fr: float | None = None
    brake_temp_rl: float | None = None
    brake_temp_rr: float | None = None


# ============================================================
# Paginated response wrapper
# ============================================================
class PaginatedResponse(BaseModel):
    items: list = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False


# ============================================================
# Car Setups
# ============================================================
class CarSetupResponse(BaseModel):
    setup_id: str
    session_id: str
    driver_id: str
    front_wing: int | None = None
    rear_wing: int | None = None
    diff_on_pct: float | None = None
    diff_off_pct: float | None = None
    front_camber: float | None = None
    rear_camber: float | None = None
    front_toe: float | None = None
    rear_toe: float | None = None
    front_suspension: int | None = None
    rear_suspension: int | None = None
    front_arb: int | None = None
    rear_arb: int | None = None
    front_ride_height: int | None = None
    rear_ride_height: int | None = None
    brake_pressure: float | None = None
    brake_bias_pct: float | None = None
    fuel_load_kg: float | None = None
    tire_pressure_fl: float | None = None
    tire_pressure_fr: float | None = None
    tire_pressure_rl: float | None = None
    tire_pressure_rr: float | None = None
    ballast: int | None = None
    created_at: datetime | None = None


# ============================================================
# Race Events
# ============================================================
class RaceEventResponse(BaseModel):
    event_id: str
    session_id: str
    driver_id: str | None = None
    lap_number: int | None = None
    event_type: str
    occurred_at: datetime | None = None
    created_at: datetime | None = None


# ============================================================
# Pit Stops
# ============================================================
class PitStopResponse(BaseModel):
    pit_id: str
    session_id: str
    driver_id: str
    lap_number: int
    duration_ms: int | None = None
    tire_from: str | None = None
    tire_to: str | None = None
    created_at: datetime | None = None


# ============================================================
# Predictions
# ============================================================
class PredictionResponse(BaseModel):
    prediction_id: str
    lap_id: str
    model_name: str
    predicted_at: datetime | None = None
    prediction: dict | None = None


# ============================================================
# Compare
# ============================================================
class DeltaPoint(BaseModel):
    distance_m: float
    speed_delta: float = 0.0
    throttle_delta: float = 0.0
    brake_delta: float = 0.0
    steering_delta: float = 0.0


class LapComparisonResponse(BaseModel):
    lap_ids: list[str]
    deltas: list[DeltaPoint] = Field(default_factory=list)
    sector_deltas: dict[str, list[float]] = Field(default_factory=dict)


class SimVsRealResponse(BaseModel):
    sim_lap_id: str
    real_lap_id: str
    circuit_id: str
    comparison: LapComparisonResponse


# ============================================================
# Predict
# ============================================================
class TireLifeRequest(BaseModel):
    tire_compound: str
    tire_age_laps: int
    avg_speed_kph: float = 200.0
    track_temp_c: float = 30.0
    fuel_load_kg: float = 50.0


class TireLifeResponse(BaseModel):
    predicted_remaining_laps: int
    degradation_rate_pct_per_lap: float
    current_grip_pct: float
    recommendation: str


class PitWindowRequest(BaseModel):
    current_lap: int
    total_laps: int
    tire_compound: str
    tire_age_laps: int
    position: int = 1
    gap_ahead_ms: int | None = None
    gap_behind_ms: int | None = None


class PitWindowResponse(BaseModel):
    optimal_pit_lap: int
    recommended_compound: str
    strategy_description: str
    undercut_viable: bool = False
    overcut_viable: bool = False


# ============================================================
# WebSocket
# ============================================================
class LiveTelemetryFrame(BaseModel):
    """Real-time telemetry frame broadcast over WebSocket."""

    session_id: str
    driver_id: str
    lap_number: int
    timestamp_ms: int
    speed_kph: float
    throttle_pct: float
    brake_pct: float
    steering: float
    gear: int
    rpm: int
    drs: int
