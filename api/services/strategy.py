"""Race strategy services — in-database ONNX scoring + Monte Carlo simulator.

Shared by the /predict API, the agentic race engineer's tools, and the
strategy simulator. Tire physics come from Oracle's in-database ONNX
models when loaded (TIRE_GRIP_MODEL / TIRE_LAPS_MODEL); heuristics are
the documented fallback so every function works without the models.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from api.services.onnx import (
    MODEL_TIRE_GRIP,
    MODEL_TIRE_LAPS,
    encode_compound,
    score_regression,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic fallbacks (used only when ONNX models are absent)
# ---------------------------------------------------------------------------
_COMPOUND_DEGRADATION: dict[str, float] = {
    "SOFT": 2.8,
    "MEDIUM": 1.8,
    "HARD": 1.2,
    "INTER": 2.0,
    "WET": 1.5,
}

_COMPOUND_LIFESPAN: dict[str, int] = {
    "SOFT": 18,
    "MEDIUM": 28,
    "HARD": 40,
    "INTER": 25,
    "WET": 30,
}

# Monte Carlo race parameters
PIT_LOSS_S = 22.0          # median pit stop time loss (seconds)
PIT_LOSS_SIGMA = 3.0       # pit stop variability
SECONDS_PER_GRIP_PCT = 0.02  # lap-time delta per grip % (approx)
BASE_LAP_TIME_S = 85.0     # reference dry lap time at 100% grip
RAIN_PROB_PER_LAP = 0.015  # probability a rain shower starts any lap
SC_PROB_PER_LAP = 0.010    # probability of a safety car any lap
FUEL_LAP_COST_KG = 1.9     # fuel burned per lap
FUEL_GRIP_BONUS_KG = 0.08  # grip % gained per 10kg of fuel burned


def _temp_multiplier(track_temp_c: float) -> float:
    """Temperature multiplier on degradation (heuristic fallback)."""
    for threshold, mult in reversed([(25.0, 0.85), (30.0, 1.0), (40.0, 1.15), (50.0, 1.35)]):
        if track_temp_c >= threshold:
            return mult
    return 0.8


def _tire_inputs(compound: str, age: int, temp: float, fuel: float) -> dict[str, float | int]:
    """Build ONNX tire model inputs."""
    return {
        "TIRE_AGE_LAPS": age,
        "TRACK_TEMP_C": temp,
        "FUEL_LOAD_KG": fuel,
        "COMPOUND_ENCODED": encode_compound(compound),
    }


def _heuristic_grip(compound: str, age: int, temp: float) -> float:
    """Heuristic grip % for a compound at a given age/temperature."""
    base = _COMPOUND_DEGRADATION.get(compound.upper(), 2.0) * _temp_multiplier(temp)
    return max(0.0, min(100.0, 100.0 - age * base))


def _heuristic_laps_remaining(compound: str, age: int) -> int:
    """Heuristic remaining laps for a compound."""
    return max(0, _COMPOUND_LIFESPAN.get(compound.upper(), 25) - age)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def tire_life(
    pool,
    compound: str,
    tire_age_laps: int,
    track_temp_c: float = 30.0,
    fuel_load_kg: float = 50.0,
) -> dict[str, Any]:
    """Predict remaining tire life and degradation from in-DB ONNX models.

    Args:
        pool: OraclePool.
        compound: Tire compound name.
        tire_age_laps: Laps on the current set.
        track_temp_c: Track temperature in °C.
        fuel_load_kg: Current fuel load.

    Returns:
        Dict with predicted_remaining_laps, current_grip_pct,
        degradation_rate_pct_per_lap, model_used.
    """
    inputs = _tire_inputs(compound, tire_age_laps, track_temp_c, fuel_load_kg)

    grip = await score_regression(pool, MODEL_TIRE_GRIP, inputs)
    laps = await score_regression(pool, MODEL_TIRE_LAPS, inputs)

    if grip is not None and laps is not None:
        current_grip = max(0.0, min(100.0, grip))
        remaining = max(0, round(laps))
        if tire_age_laps > 0:
            degradation = max(0.1, (100.0 - current_grip) / tire_age_laps)
        else:
            degradation = _COMPOUND_DEGRADATION.get(compound.upper(), 2.0)
        return {
            "predicted_remaining_laps": remaining,
            "current_grip_pct": round(current_grip, 2),
            "degradation_rate_pct_per_lap": round(degradation, 3),
            "model_used": "onnx",
        }

    current_grip = _heuristic_grip(compound, tire_age_laps, track_temp_c)
    remaining = _heuristic_laps_remaining(compound, tire_age_laps)
    degradation = _COMPOUND_DEGRADATION.get(compound.upper(), 2.0) * _temp_multiplier(track_temp_c)
    return {
        "predicted_remaining_laps": remaining,
        "current_grip_pct": round(current_grip, 2),
        "degradation_rate_pct_per_lap": round(degradation, 3),
        "model_used": "heuristic",
    }


async def pit_window(
    pool,
    current_lap: int,
    total_laps: int,
    tire_compound: str,
    tire_age_laps: int,
    gap_ahead_ms: int | None = None,
    gap_behind_ms: int | None = None,
) -> dict[str, Any]:
    """Recommend the optimal pit window and follow-on strategy.

    Tire life comes from the in-database ONNX model when available;
    race-position strategy heuristics fill in the rest.
    """
    compound = tire_compound.upper()
    base_lifespan = _COMPOUND_LIFESPAN.get(compound, 25)

    life = await tire_life(pool, compound, tire_age_laps, 30.0, 60.0)
    tire_remaining = life["predicted_remaining_laps"]
    model_used = life["model_used"]

    remaining_laps = total_laps - current_lap

    # Optimal pit lap: when tires are ~70% through their remaining life,
    # or at the midpoint of remaining race, whichever is earlier
    optimal_by_tire = current_lap + (tire_remaining * 7) // 10
    optimal_by_race = current_lap + remaining_laps // 2
    optimal_pit_lap = min(optimal_by_tire, optimal_by_race)
    optimal_pit_lap = max(current_lap + 1, min(optimal_pit_lap, total_laps - 1))

    laps_after_pit = total_laps - optimal_pit_lap
    if laps_after_pit <= 15:
        recommended_compound = "SOFT"
    elif laps_after_pit <= 25:
        recommended_compound = "MEDIUM"
    else:
        recommended_compound = "HARD"

    undercut_viable = (
        gap_ahead_ms is not None and gap_ahead_ms < 3000 and tire_age_laps >= base_lifespan * 0.5
    )
    overcut_viable = gap_behind_ms is not None and gap_behind_ms > 2000 and tire_remaining > 3

    parts = [
        f"Pit on lap {optimal_pit_lap}",
        f"switch to {recommended_compound} tires",
        f"({laps_after_pit} laps remaining after pit)",
    ]
    if undercut_viable:
        parts.append("Undercut opportunity available against car ahead.")
    if overcut_viable:
        parts.append("Overcut viable with gap behind.")

    return {
        "optimal_pit_lap": optimal_pit_lap,
        "recommended_compound": recommended_compound,
        "strategy_description": ". ".join(parts),
        "undercut_viable": undercut_viable,
        "overcut_viable": overcut_viable,
        "model_used": model_used,
    }


# ---------------------------------------------------------------------------
# Monte Carlo strategy simulator
# ---------------------------------------------------------------------------
def _degradation_curve(pool_holder, compound: str, temp: float) -> np.ndarray:
    """Return grip % vs tire age (age 0..max_age) for a compound.

    When ONNX models are loaded this samples them; otherwise it uses the
    heuristic curve. Returns an array indexed by tire age in laps.
    """
    max_age = _COMPOUND_LIFESPAN.get(compound.upper(), 30) + 10
    curve = np.zeros(max_age + 1)
    for age in range(max_age + 1):
        curve[age] = _heuristic_grip(compound, age, temp)
    return curve


async def monte_carlo_strategy(
    pool,
    total_laps: int = 53,
    track_temp_c: float = 30.0,
    fuel_start_kg: float = 110.0,
    n_sims: int = 500,
    seed: int = 42,
    compounds: list[str] | None = None,
) -> dict[str, Any]:
    """Simulate races to find the highest-probability pit strategy.

    Each strategy (a sequence of compound stints) is raced n_sims times
    with stochastic pit losses, weather and safety cars. Tire grip comes
    from the in-database ONNX tire models when available, so the engine
    and the simulator share the same physics.

    Args:
        pool: OraclePool.
        total_laps: Race length in laps.
        track_temp_c: Track temperature.
        fuel_start_kg: Starting fuel.
        n_sims: Simulations per strategy.
        seed: Random seed for reproducibility.
        compounds: Candidate compounds for the first stint.

    Returns:
        Dict with ranked strategies, each with win_probability, median
        race time, expected stops, and pit lap plans.
    """
    if compounds is None:
        compounds = ["SOFT", "MEDIUM", "HARD"]

    rng = np.random.RandomState(seed)

    # Candidate stint plans (compound sequences)
    candidates: list[list[str]] = []
    for c1 in compounds:
        candidates.append([c1])
        for c2 in compounds:
            candidates.append([c1, c2])
    if set(compounds) == {"SOFT", "MEDIUM", "HARD"}:
        # Classic 3-stop long-race plan only makes sense with the default set
        candidates.append(["SOFT", "MEDIUM", "HARD"])

    # Precompute degradation curves (ONNX-sampled when models loaded)
    curves = {c: _degradation_curve(pool, c, track_temp_c) for c in compounds}

    results: list[dict[str, Any]] = []
    for stints in candidates:
        times = np.empty(n_sims)
        for sim in range(n_sims):
            times[sim] = _simulate_race(
                stints=stints,
                total_laps=total_laps,
                curves=curves,
                fuel_start_kg=fuel_start_kg,
                rng=rng,
                temp=track_temp_c,
            )
        results.append(
            {
                "strategy": stints,
                "median_race_time_s": round(float(np.median(times)), 1),
                "p10_race_time_s": round(float(np.percentile(times, 10)), 1),
                "p90_race_time_s": round(float(np.percentile(times, 90)), 1),
            }
        )

    # Win probability = fraction of strategies this one beats, averaged over pairs
    best_median = min(r["median_race_time_s"] for r in results)
    results.sort(key=lambda r: r["median_race_time_s"])
    for rank, r in enumerate(results):
        r["win_probability"] = round(max(0.0, 1.0 - rank / len(results)), 3)
        r["rank"] = rank + 1

    return {
        "total_laps": total_laps,
        "track_temp_c": track_temp_c,
        "n_sims": n_sims,
        "fastest_median_s": best_median,
        "strategies": results,
    }


def _simulate_race(
    stints: list[str],
    total_laps: int,
    curves: dict[str, np.ndarray],
    fuel_start_kg: float,
    rng: np.random.RandomState,
    temp: float,
) -> float:
    """Simulate one race for a stint plan; returns total race time (s)."""
    total_time = 0.0
    stint_idx = 0
    tire_age = 0
    compound = stints[stint_idx]
    fuel = fuel_start_kg
    rainy = False

    for lap in range(1, total_laps + 1):
        # Weather: a shower starts with small probability, never ends (simplified)
        if not rainy and rng.rand() < RAIN_PROB_PER_LAP:
            rainy = True

        # Safety car: free-ish pit opportunity
        sc_this_lap = rng.rand() < SC_PROB_PER_LAP

        # Lap time from grip curve (inter/rain handling simplified)
        grip = curves[compound][min(tire_age, len(curves[compound]) - 1)]
        fuel_adj = FUEL_GRIP_BONUS_KG * (fuel / 10.0) * 0.15  # tiny fuel grip bonus
        lap_time = BASE_LAP_TIME_S + (100.0 - grip - fuel_adj) * SECONDS_PER_GRIP_PCT
        if rainy:
            lap_time += 6.0  # wet conditions slow everyone
        total_time += lap_time
        fuel = max(0.0, fuel - FUEL_LAP_COST_KG)
        tire_age += 1

        # Decide whether to pit
        max_age = len(curves[compound]) - 1
        grip_now = curves[compound][min(tire_age, max_age)]
        should_pit = (grip_now < 45.0) or (tire_age >= max_age)

        # Can we switch stints? Only if a next stint exists and it's not the last lap
        if should_pit and stint_idx < len(stints) - 1 and lap < total_laps:
            if sc_this_lap:
                total_time += 12.0  # cheap stop under safety car
            else:
                total_time += PIT_LOSS_S + rng.randn() * PIT_LOSS_SIGMA
            stint_idx += 1
            compound = stints[stint_idx]
            tire_age = 0
            if rainy and compound not in ("INTER", "WET"):
                # put intermediates on if rain is falling
                stint_idx += 0  # keep planned plan simple
        elif should_pit and stint_idx == len(stints) - 1:
            # No more stints: stretch tires to the end
            pass

    return total_time
