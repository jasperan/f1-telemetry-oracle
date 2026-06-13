"""Laps router — list laps, retrieve telemetry frames, and vector similarity search."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.db.columns import FRAME_COLUMNS as _FRAME_COLUMNS
from api.db.columns import LAP_COLUMNS as _LAP_COLUMNS
from api.models.schemas import (
    LapResponse,
    PaginatedResponse,
    SimilarLapResponse,
    TelemetryFrameResponse,
)

router = APIRouter(prefix="/laps", tags=["laps"])


def _row_to_lap(row: tuple) -> LapResponse:
    """Map a DB row tuple to LapResponse."""
    return LapResponse(
        lap_id=row[0],
        session_id=row[1],
        driver_id=row[2],
        lap_number=row[3],
        sector1_ms=row[4],
        sector2_ms=row[5],
        sector3_ms=row[6],
        lap_time_ms=row[7],
        tire_compound=row[8],
        tire_age_laps=row[9],
        fuel_load_kg=row[10],
        ers_deploy_pct=row[11],
        is_valid=bool(row[12]),
        position=row[13],
        created_at=row[14],
    )


_LAP_COLUMNS_ALIASED = ", ".join(
    f"l.{col.strip()}" for col in _LAP_COLUMNS.split(",")
)


def _row_to_frame(row: tuple) -> TelemetryFrameResponse:
    """Map a DB row tuple to TelemetryFrameResponse."""
    return TelemetryFrameResponse(
        frame_id=row[0],
        lap_id=row[1],
        timestamp_ms=row[2],
        distance_m=row[3],
        speed_kph=row[4],
        throttle_pct=row[5],
        brake_pct=row[6],
        steering=row[7],
        gear=row[8],
        rpm=row[9],
        drs=row[10],
        pos_x=row[11],
        pos_y=row[12],
        pos_z=row[13],
        g_lat=row[14],
        g_lon=row[15],
        tire_temp_fl=row[16],
        tire_temp_fr=row[17],
        tire_temp_rl=row[18],
        tire_temp_rr=row[19],
        brake_temp_fl=row[20],
        brake_temp_fr=row[21],
        brake_temp_rl=row[22],
        brake_temp_rr=row[23],
    )


@router.get("", response_model=list[LapResponse])
async def list_laps(
    request: Request,
    session_id: str | None = Query(None, description="Filter by session ID"),
    driver_id: str | None = Query(None, description="Filter by driver ID"),
    source: str | None = Query(None, description="Filter by source (via session join)"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Number of rows to skip"),
) -> list[LapResponse]:
    """Return laps with optional filters."""
    pool = request.app.state.pool

    # Always join sessions so every filter can use stable l./s. prefixes
    # (laps.session_id is a FK to sessions, so the join is row-preserving).
    base_sql = (
        f"SELECT {_LAP_COLUMNS_ALIASED} "
        f"FROM laps l JOIN sessions s ON l.session_id = s.session_id"
    )

    # Collect (column, value) filter pairs, then assign positional bind
    # indexes in order so the SQL and params list stay in lockstep.
    filters: list[tuple[str, object]] = []
    if session_id is not None:
        filters.append(("l.session_id", session_id))
    if driver_id is not None:
        filters.append(("l.driver_id", driver_id))
    if source is not None:
        filters.append(("s.source", source))

    params: list = []
    if filters:
        conditions = []
        for column, value in filters:
            params.append(value)
            conditions.append(f"{column} = :{len(params)}")
        base_sql += " WHERE " + " AND ".join(conditions)

    base_sql += " ORDER BY l.lap_number"
    params.append(offset)
    offset_idx = len(params)
    params.append(limit)
    limit_idx = len(params)
    base_sql += f" OFFSET :{offset_idx} ROWS FETCH FIRST :{limit_idx} ROWS ONLY"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(base_sql, params)
        rows = await cursor.fetchall()
    return [_row_to_lap(r) for r in rows]


@router.get("/{lap_id}", response_model=LapResponse)
async def get_lap(lap_id: str, request: Request) -> LapResponse:
    """Return a single lap with sector times."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            f"SELECT {_LAP_COLUMNS} FROM laps WHERE lap_id = :1",
            [lap_id],
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Lap {lap_id!r} not found")
    return _row_to_lap(row)


@router.get("/{lap_id}/telemetry", response_model=PaginatedResponse)
async def get_lap_telemetry(
    lap_id: str,
    request: Request,
    cursor_after: int | None = Query(None, description="Cursor: timestamp_ms to start after"),
    page_size: int = Query(1000, ge=1, le=5000, description="Number of frames per page"),
) -> PaginatedResponse:
    """Return telemetry frames for a lap with cursor-based pagination."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        db_cursor = conn.cursor()

        # First verify the lap exists
        await db_cursor.execute("SELECT lap_id FROM laps WHERE lap_id = :1", [lap_id])
        if await db_cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Lap {lap_id!r} not found")

        # Build query with cursor-based pagination
        if cursor_after is not None:
            sql = (
                f"SELECT {_FRAME_COLUMNS} FROM telemetry_frames "
                f"WHERE lap_id = :1 AND timestamp_ms > :2 "
                f"ORDER BY timestamp_ms FETCH FIRST :3 ROWS ONLY"
            )
            params: list = [lap_id, cursor_after, page_size + 1]
        else:
            sql = (
                f"SELECT {_FRAME_COLUMNS} FROM telemetry_frames "
                f"WHERE lap_id = :1 "
                f"ORDER BY timestamp_ms FETCH FIRST :2 ROWS ONLY"
            )
            params = [lap_id, page_size + 1]

        await db_cursor.execute(sql, params)
        rows = await db_cursor.fetchall()

    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    frames = [_row_to_frame(r) for r in rows]

    return PaginatedResponse(
        items=[f.model_dump() for f in frames],
        total=len(frames),
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/{lap_id}/similar", response_model=list[SimilarLapResponse])
async def get_similar_laps(
    lap_id: str,
    request: Request,
    top_n: int = Query(5, ge=1, le=50, description="Number of similar laps to return"),
) -> list[SimilarLapResponse]:
    """Return N most similar laps by vector distance on lap_embedding."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        db_cursor = conn.cursor()

        # First get the target lap's embedding
        await db_cursor.execute(
            "SELECT lap_embedding FROM laps WHERE lap_id = :1",
            [lap_id],
        )
        target_row = await db_cursor.fetchone()
        if target_row is None:
            raise HTTPException(status_code=404, detail=f"Lap {lap_id!r} not found")

        if target_row[0] is None:
            raise HTTPException(
                status_code=422,
                detail=f"Lap {lap_id!r} has no embedding vector",
            )

        # Vector similarity search using Oracle AI Vector Search
        # VECTOR_DISTANCE returns cosine distance by default
        sql = (
            f"SELECT {_LAP_COLUMNS}, "
            f"VECTOR_DISTANCE(lap_embedding, (SELECT lap_embedding FROM laps WHERE lap_id = :1), COSINE) AS dist "
            f"FROM laps "
            f"WHERE lap_id != :2 AND lap_embedding IS NOT NULL "
            f"ORDER BY dist "
            f"FETCH FIRST :3 ROWS ONLY"
        )
        await db_cursor.execute(sql, [lap_id, lap_id, top_n])
        rows = await db_cursor.fetchall()

    results = []
    for row in rows:
        lap = _row_to_lap(row[:15])
        distance = float(row[15])
        results.append(SimilarLapResponse(lap=lap, distance=distance))
    return results
