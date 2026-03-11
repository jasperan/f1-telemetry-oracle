"""Sessions router — list and retrieve session metadata."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.models.schemas import SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _row_to_session(row: tuple) -> SessionResponse:
    """Map a DB row tuple to SessionResponse."""
    return SessionResponse(
        session_id=row[0],
        circuit_id=row[1],
        session_type=row[2],
        source=row[3],
        season=row[4],
        round_number=row[5],
        air_temp_c=row[6],
        track_temp_c=row[7],
        started_at=row[8],
        created_at=row[9],
    )


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    request: Request,
    source: str | None = Query(None, description="Filter by source: sim, openf1, ergast"),
    circuit_id: str | None = Query(None, description="Filter by circuit ID"),
    season: int | None = Query(None, description="Filter by season year"),
) -> list[SessionResponse]:
    """Return sessions with optional filters."""
    pool = request.app.state.pool
    base_sql = (
        "SELECT session_id, circuit_id, session_type, source, "
        "season, round_number, air_temp_c, track_temp_c, started_at, created_at "
        "FROM sessions"
    )
    conditions: list[str] = []
    params: list = []
    idx = 1

    if source is not None:
        conditions.append(f"source = :{idx}")
        params.append(source)
        idx += 1
    if circuit_id is not None:
        conditions.append(f"circuit_id = :{idx}")
        params.append(circuit_id)
        idx += 1
    if season is not None:
        conditions.append(f"season = :{idx}")
        params.append(season)
        idx += 1

    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)
    base_sql += " ORDER BY created_at DESC"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(base_sql, params)
        rows = await cursor.fetchall()
    return [_row_to_session(r) for r in rows]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    """Return a single session by ID."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT session_id, circuit_id, session_type, source, "
            "season, round_number, air_temp_c, track_temp_c, started_at, created_at "
            "FROM sessions WHERE session_id = :1",
            [session_id],
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return _row_to_session(row)
