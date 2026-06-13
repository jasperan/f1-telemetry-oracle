"""Compare router — compare laps side-by-side, including sim-vs-real analysis."""

from __future__ import annotations

import bisect
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.db.columns import FRAME_COLUMNS as _FRAME_COLUMNS
from api.db.columns import LAP_COLUMNS as _LAP_COLUMNS
from api.models.schemas import DeltaPoint, LapComparisonResponse, SimVsRealResponse

router = APIRouter(prefix="/compare", tags=["compare"])


# ============================================================
# Telemetry alignment helpers
# ============================================================
def _interpolate_at(distances: list[float], values: list[float], target_d: float) -> float:
    """Linearly interpolate a value at target_d given parallel distance/value arrays."""
    if not distances:
        return 0.0
    if target_d <= distances[0]:
        return values[0]
    if target_d >= distances[-1]:
        return values[-1]
    idx = bisect.bisect_right(distances, target_d)
    d0, d1 = distances[idx - 1], distances[idx]
    v0, v1 = values[idx - 1], values[idx]
    if d1 == d0:
        return v0
    ratio = (target_d - d0) / (d1 - d0)
    return v0 + ratio * (v1 - v0)


def _align_telemetry(
    frames_a: list[tuple],
    frames_b: list[tuple],
    step_m: float = 10.0,
) -> list[DeltaPoint]:
    """Align two telemetry traces by distance_m, interpolating, and compute deltas.

    Frame tuple layout (from telemetry_frames):
    [0]=frame_id, [1]=lap_id, [2]=timestamp_ms, [3]=distance_m,
    [4]=speed_kph, [5]=throttle_pct, [6]=brake_pct, [7]=steering, ...
    """
    if not frames_a or not frames_b:
        return []

    # Extract channels
    dist_a = [float(f[3] or 0) for f in frames_a]
    dist_b = [float(f[3] or 0) for f in frames_b]

    speed_a = [float(f[4] or 0) for f in frames_a]
    speed_b = [float(f[4] or 0) for f in frames_b]
    throttle_a = [float(f[5] or 0) for f in frames_a]
    throttle_b = [float(f[5] or 0) for f in frames_b]
    brake_a = [float(f[6] or 0) for f in frames_a]
    brake_b = [float(f[6] or 0) for f in frames_b]
    steer_a = [float(f[7] or 0) for f in frames_a]
    steer_b = [float(f[7] or 0) for f in frames_b]

    # Determine common distance range
    d_start = max(min(dist_a), min(dist_b))
    d_end = min(max(dist_a), max(dist_b))

    if d_end <= d_start:
        return []

    deltas: list[DeltaPoint] = []
    d = d_start
    while d <= d_end:
        deltas.append(DeltaPoint(
            distance_m=round(d, 2),
            speed_delta=round(
                _interpolate_at(dist_a, speed_a, d) - _interpolate_at(dist_b, speed_b, d), 3
            ),
            throttle_delta=round(
                _interpolate_at(dist_a, throttle_a, d) - _interpolate_at(dist_b, throttle_b, d), 4
            ),
            brake_delta=round(
                _interpolate_at(dist_a, brake_a, d) - _interpolate_at(dist_b, brake_b, d), 4
            ),
            steering_delta=round(
                _interpolate_at(dist_a, steer_a, d) - _interpolate_at(dist_b, steer_b, d), 4
            ),
        ))
        d += step_m

    return deltas


def _compute_sector_deltas(
    lap_rows: list[tuple],
) -> dict[str, list[float]]:
    """Compute per-sector time deltas across laps.

    lap_row layout: [0]=lap_id, ..., [4]=sector1_ms, [5]=sector2_ms, [6]=sector3_ms, ...
    Returns {"sector1_ms": [lap1_s1, lap2_s1, ...], ...}
    """
    sector_deltas: dict[str, list[float]] = {
        "sector1_ms": [],
        "sector2_ms": [],
        "sector3_ms": [],
    }
    for row in lap_rows:
        sector_deltas["sector1_ms"].append(float(row[4]) if row[4] is not None else 0.0)
        sector_deltas["sector2_ms"].append(float(row[5]) if row[5] is not None else 0.0)
        sector_deltas["sector3_ms"].append(float(row[6]) if row[6] is not None else 0.0)
    return sector_deltas


async def _fetch_frames(pool: Any, lap_id: str) -> list[tuple]:
    """Fetch all telemetry frames for a lap, ordered by distance_m."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            f"SELECT {_FRAME_COLUMNS} FROM telemetry_frames "
            f"WHERE lap_id = :1 ORDER BY distance_m",
            [lap_id],
        )
        return await cursor.fetchall()


async def _fetch_lap_row(pool: Any, lap_id: str) -> tuple | None:
    """Fetch a single lap row."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            f"SELECT {_LAP_COLUMNS} FROM laps WHERE lap_id = :1",
            [lap_id],
        )
        return await cursor.fetchone()


@router.get("/laps", response_model=LapComparisonResponse)
async def compare_laps(
    request: Request,
    ids: str = Query(..., description="Comma-separated lap IDs to compare"),
) -> LapComparisonResponse:
    """Compare telemetry for multiple laps, aligned by distance_m."""
    pool = request.app.state.pool
    lap_ids = [lid.strip() for lid in ids.split(",") if lid.strip()]

    if len(lap_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 lap IDs are required")

    # Fetch lap rows for sector deltas
    lap_rows: list[tuple] = []
    for lid in lap_ids:
        row = await _fetch_lap_row(pool, lid)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Lap {lid!r} not found")
        lap_rows.append(row)

    sector_deltas = _compute_sector_deltas(lap_rows)

    # Fetch telemetry and compute deltas between first and second lap
    frames_a = await _fetch_frames(pool, lap_ids[0])
    frames_b = await _fetch_frames(pool, lap_ids[1])
    deltas = _align_telemetry(frames_a, frames_b)

    return LapComparisonResponse(
        lap_ids=lap_ids,
        deltas=deltas,
        sector_deltas=sector_deltas,
    )


@router.get("/sim-vs-real", response_model=SimVsRealResponse)
async def sim_vs_real(
    request: Request,
    lap_id: str = Query(..., description="Sim lap ID to compare"),
) -> SimVsRealResponse:
    """Find the best matching real-world lap at the same circuit and compare."""
    pool = request.app.state.pool

    # Fetch the sim lap and its session to find the circuit
    sim_lap = await _fetch_lap_row(pool, lap_id)
    if sim_lap is None:
        raise HTTPException(status_code=404, detail=f"Lap {lap_id!r} not found")

    session_id = sim_lap[1]  # session_id

    # Get the circuit_id and verify source is sim
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT circuit_id, source FROM sessions WHERE session_id = :1",
            [session_id],
        )
        session_row = await cursor.fetchone()

    if session_row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    circuit_id = session_row[0]
    source = session_row[1]

    if source != "sim":
        raise HTTPException(
            status_code=400,
            detail=f"Lap {lap_id!r} is from source {source!r}, not 'sim'. Use /compare/laps for general comparison.",
        )

    # Find the best matching real-world lap at the same circuit
    # "Best matching" = closest lap_time_ms among valid real-world laps
    sim_lap_time = sim_lap[7]  # lap_time_ms

    async with pool.connection() as conn:
        cursor = conn.cursor()
        if sim_lap_time is not None:
            await cursor.execute(
                f"SELECT {_LAP_COLUMNS} FROM laps l "
                f"JOIN sessions s ON l.session_id = s.session_id "
                f"WHERE s.circuit_id = :1 AND s.source != 'sim' "
                f"AND l.is_valid = 1 AND l.lap_time_ms IS NOT NULL "
                f"ORDER BY ABS(l.lap_time_ms - :2) "
                f"FETCH FIRST 1 ROWS ONLY",
                [circuit_id, sim_lap_time],
            )
        else:
            # No sim lap time — just pick the fastest real lap at this circuit
            await cursor.execute(
                f"SELECT {_LAP_COLUMNS} FROM laps l "
                f"JOIN sessions s ON l.session_id = s.session_id "
                f"WHERE s.circuit_id = :1 AND s.source != 'sim' "
                f"AND l.is_valid = 1 AND l.lap_time_ms IS NOT NULL "
                f"ORDER BY l.lap_time_ms "
                f"FETCH FIRST 1 ROWS ONLY",
                [circuit_id],
            )
        real_row = await cursor.fetchone()

    if real_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No real-world lap found at circuit {circuit_id!r} for comparison",
        )

    real_lap_id = real_row[0]

    # Fetch telemetry for both laps and align
    frames_sim = await _fetch_frames(pool, lap_id)
    frames_real = await _fetch_frames(pool, real_lap_id)
    deltas = _align_telemetry(frames_sim, frames_real)

    sector_deltas = _compute_sector_deltas([sim_lap, real_row])

    comparison = LapComparisonResponse(
        lap_ids=[lap_id, real_lap_id],
        deltas=deltas,
        sector_deltas=sector_deltas,
    )

    return SimVsRealResponse(
        sim_lap_id=lap_id,
        real_lap_id=real_lap_id,
        circuit_id=circuit_id,
        comparison=comparison,
    )
