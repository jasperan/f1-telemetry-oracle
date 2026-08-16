"""Predict router — tire life, pit window, and strategy simulation.

Tire physics are scored by Oracle's in-database ONNX models
(TIRE_GRIP_MODEL / TIRE_LAPS_MODEL) with a heuristic fallback; see
api/services/strategy.py. The strategy-sim endpoint runs a Monte Carlo
simulation over candidate pit strategies using the same in-DB physics.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.models.schemas import (
    PitWindowRequest,
    PitWindowResponse,
    StrategySimRequest,
    StrategySimResponse,
    TireLifeRequest,
    TireLifeResponse,
)
from api.services import strategy

router = APIRouter(prefix="/predict", tags=["predict"])


@router.post("/tire-life", response_model=TireLifeResponse)
async def predict_tire_life(request: Request, req: TireLifeRequest) -> TireLifeResponse:
    """Predict remaining tire life and degradation rate.

    In-database ONNX inference (TIRE_GRIP_MODEL + TIRE_LAPS_MODEL) when
    the models are loaded; heuristic fallback otherwise.
    """
    result = await strategy.tire_life(
        request.app.state.pool,
        compound=req.tire_compound,
        tire_age_laps=req.tire_age_laps,
        track_temp_c=req.track_temp_c,
        fuel_load_kg=req.fuel_load_kg,
    )

    current_grip = result["current_grip_pct"]
    remaining = result["predicted_remaining_laps"]
    return TireLifeResponse(
        predicted_remaining_laps=remaining,
        degradation_rate_pct_per_lap=result["degradation_rate_pct_per_lap"],
        current_grip_pct=current_grip,
        recommendation=_tire_recommendation(current_grip, remaining),
        model_used=result["model_used"],
    )


@router.post("/pit-window", response_model=PitWindowResponse)
async def predict_pit_window(request: Request, req: PitWindowRequest) -> PitWindowResponse:
    """Predict optimal pit stop window and tire strategy."""
    result = await strategy.pit_window(
        request.app.state.pool,
        current_lap=req.current_lap,
        total_laps=req.total_laps,
        tire_compound=req.tire_compound,
        tire_age_laps=req.tire_age_laps,
        gap_ahead_ms=req.gap_ahead_ms,
        gap_behind_ms=req.gap_behind_ms,
    )
    return PitWindowResponse(
        optimal_pit_lap=result["optimal_pit_lap"],
        recommended_compound=result["recommended_compound"],
        strategy_description=result["strategy_description"],
        undercut_viable=result["undercut_viable"],
        overcut_viable=result["overcut_viable"],
        model_used=result["model_used"],
    )


@router.post("/strategy-sim", response_model=StrategySimResponse)
async def simulate_strategy(request: Request, req: StrategySimRequest) -> StrategySimResponse:
    """Run a Monte Carlo simulation to find the optimal pit strategy."""
    result = await strategy.monte_carlo_strategy(
        request.app.state.pool,
        total_laps=req.total_laps,
        track_temp_c=req.track_temp_c,
        fuel_start_kg=req.fuel_start_kg,
        n_sims=req.n_sims,
        seed=req.seed,
        compounds=req.compounds,
    )
    return StrategySimResponse(**result)


def _tire_recommendation(current_grip_pct: float, remaining_laps: int) -> str:
    """Turn grip/laps numbers into an engineer-style recommendation."""
    if current_grip_pct < 30.0:
        return "CRITICAL: Pit immediately, tire grip severely compromised"
    if current_grip_pct < 50.0:
        return "WARNING: Consider pitting within 2-3 laps"
    if remaining_laps <= 5:
        return "MONITOR: Tires approaching end of life"
    return f"OK: Tires have ~{remaining_laps} laps remaining at current pace"
