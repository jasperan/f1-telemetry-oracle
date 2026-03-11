"""Drivers router — list and retrieve driver metadata."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.models.schemas import DriverResponse

router = APIRouter(prefix="/drivers", tags=["drivers"])


def _row_to_driver(row: tuple) -> DriverResponse:
    """Map a DB row tuple to DriverResponse."""
    return DriverResponse(
        driver_id=row[0],
        code=row[1],
        first_name=row[2],
        last_name=row[3],
        driver_number=row[4],
        nationality=row[5],
        is_sim_player=bool(row[6]),
        created_at=row[7],
    )


@router.get("", response_model=list[DriverResponse])
async def list_drivers(
    request: Request,
    nationality: str | None = Query(None, description="Filter by nationality"),
    is_sim_player: bool | None = Query(None, description="Filter by sim player flag"),
) -> list[DriverResponse]:
    """Return drivers with optional filters."""
    pool = request.app.state.pool
    base_sql = (
        "SELECT driver_id, code, first_name, last_name, "
        "driver_number, nationality, is_sim_player, created_at "
        "FROM drivers"
    )
    conditions: list[str] = []
    params: list = []
    idx = 1

    if nationality is not None:
        conditions.append(f"nationality = :{idx}")
        params.append(nationality)
        idx += 1
    if is_sim_player is not None:
        conditions.append(f"is_sim_player = :{idx}")
        params.append(1 if is_sim_player else 0)
        idx += 1

    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)
    base_sql += " ORDER BY last_name, first_name"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(base_sql, params)
        rows = await cursor.fetchall()
    return [_row_to_driver(r) for r in rows]


@router.get("/{driver_id}", response_model=DriverResponse)
async def get_driver(driver_id: str, request: Request) -> DriverResponse:
    """Return a single driver by ID."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT driver_id, code, first_name, last_name, "
            "driver_number, nationality, is_sim_player, created_at "
            "FROM drivers WHERE driver_id = :1",
            [driver_id],
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Driver {driver_id!r} not found")
    return _row_to_driver(row)
