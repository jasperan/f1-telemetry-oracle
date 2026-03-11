"""Predict router — tire life and pit window heuristic models.

These endpoints provide heuristic-based predictions as placeholders until
ONNX models are loaded for ML-based inference.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.models.schemas import (
    PitWindowRequest,
    PitWindowResponse,
    TireLifeRequest,
    TireLifeResponse,
)

router = APIRouter(prefix="/predict", tags=["predict"])


# ============================================================
# Tire degradation heuristic constants
# ============================================================
# Base expected lifespan (laps) by compound
_COMPOUND_LIFESPAN: dict[str, int] = {
    "SOFT": 18,
    "MEDIUM": 28,
    "HARD": 40,
    "INTER": 25,
    "WET": 30,
}

# Degradation rate (% grip loss per lap) by compound
_COMPOUND_DEGRADATION: dict[str, float] = {
    "SOFT": 2.8,
    "MEDIUM": 1.8,
    "HARD": 1.2,
    "INTER": 2.0,
    "WET": 1.5,
}

# Temperature multiplier: hotter track = faster degradation
_TEMP_THRESHOLDS = [(25.0, 0.85), (30.0, 1.0), (40.0, 1.15), (50.0, 1.35)]

# Fuel effect: heavier car = more tire wear
_FUEL_FACTOR_PER_KG = 0.002  # +0.2% degradation per kg over baseline (30 kg)


def _temp_multiplier(track_temp_c: float) -> float:
    """Calculate temperature-based degradation multiplier."""
    for threshold, mult in reversed(_TEMP_THRESHOLDS):
        if track_temp_c >= threshold:
            return mult
    return 0.8


@router.post("/tire-life", response_model=TireLifeResponse)
async def predict_tire_life(req: TireLifeRequest) -> TireLifeResponse:
    """Predict remaining tire life and degradation rate.

    Uses a heuristic model based on compound characteristics,
    track temperature, and fuel load. Will be replaced by ONNX
    inference once the model is trained and deployed.
    """
    compound = req.tire_compound.upper()
    base_lifespan = _COMPOUND_LIFESPAN.get(compound, 25)
    base_degradation = _COMPOUND_DEGRADATION.get(compound, 2.0)

    # Adjust for temperature
    temp_mult = _temp_multiplier(req.track_temp_c)
    adjusted_degradation = base_degradation * temp_mult

    # Adjust for fuel load (baseline 30 kg)
    fuel_delta = max(0.0, req.fuel_load_kg - 30.0)
    adjusted_degradation += fuel_delta * _FUEL_FACTOR_PER_KG

    # Calculate remaining laps
    current_grip = max(0.0, 100.0 - (req.tire_age_laps * adjusted_degradation))
    remaining_laps = max(0, int(current_grip / adjusted_degradation))

    # Recommendation logic
    if current_grip < 30.0:
        recommendation = "CRITICAL: Pit immediately, tire grip severely compromised"
    elif current_grip < 50.0:
        recommendation = "WARNING: Consider pitting within 2-3 laps"
    elif remaining_laps <= 5:
        recommendation = "MONITOR: Tires approaching end of life"
    else:
        recommendation = f"OK: Tires have ~{remaining_laps} laps remaining at current pace"

    return TireLifeResponse(
        predicted_remaining_laps=remaining_laps,
        degradation_rate_pct_per_lap=round(adjusted_degradation, 3),
        current_grip_pct=round(current_grip, 2),
        recommendation=recommendation,
    )


@router.post("/pit-window", response_model=PitWindowResponse)
async def predict_pit_window(req: PitWindowRequest) -> PitWindowResponse:
    """Predict optimal pit stop window and tire strategy.

    Uses a heuristic model considering tire age, position,
    gaps, and remaining race distance. Will be enhanced with
    ML-based strategy optimization.
    """
    compound = req.tire_compound.upper()
    base_lifespan = _COMPOUND_LIFESPAN.get(compound, 25)
    base_degradation = _COMPOUND_DEGRADATION.get(compound, 2.0)

    remaining_laps = req.total_laps - req.current_lap
    tire_remaining = max(0, base_lifespan - req.tire_age_laps)

    # Optimal pit lap: when tires are ~70% through lifespan,
    # or at the midpoint of remaining race, whichever is earlier
    optimal_by_tire = req.current_lap + tire_remaining
    optimal_by_race = req.current_lap + remaining_laps // 2
    optimal_pit_lap = min(optimal_by_tire, optimal_by_race)

    # Ensure we don't suggest pitting on the last lap or after the race
    optimal_pit_lap = min(optimal_pit_lap, req.total_laps - 1)
    optimal_pit_lap = max(optimal_pit_lap, req.current_lap + 1)

    # Determine recommended compound for the second stint
    laps_after_pit = req.total_laps - optimal_pit_lap
    if laps_after_pit <= 15:
        recommended_compound = "SOFT"
    elif laps_after_pit <= 25:
        recommended_compound = "MEDIUM"
    else:
        recommended_compound = "HARD"

    # Undercut/overcut analysis
    undercut_viable = (
        req.gap_ahead_ms is not None
        and req.gap_ahead_ms < 3000
        and req.tire_age_laps >= base_lifespan * 0.5
    )
    overcut_viable = (
        req.gap_behind_ms is not None
        and req.gap_behind_ms > 2000
        and tire_remaining > 3
    )

    # Build strategy description
    parts = [
        f"Pit on lap {optimal_pit_lap}",
        f"switch to {recommended_compound} tires",
        f"({laps_after_pit} laps remaining after pit)",
    ]
    if undercut_viable:
        parts.append("Undercut opportunity available against car ahead.")
    if overcut_viable:
        parts.append("Overcut viable with gap behind.")

    return PitWindowResponse(
        optimal_pit_lap=optimal_pit_lap,
        recommended_compound=recommended_compound,
        strategy_description=". ".join(parts),
        undercut_viable=undercut_viable,
        overcut_viable=overcut_viable,
    )
