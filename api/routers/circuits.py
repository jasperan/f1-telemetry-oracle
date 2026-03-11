"""Circuits router — list and retrieve circuit metadata."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.models.schemas import CircuitResponse

router = APIRouter(prefix="/circuits", tags=["circuits"])


def _row_to_circuit(row: tuple) -> CircuitResponse:
    """Map a DB row tuple to CircuitResponse."""
    return CircuitResponse(
        circuit_id=row[0],
        circuit_name=row[1],
        country=row[2],
        locality=row[3],
        track_length_m=row[4],
        lat=row[5],
        lng=row[6],
        created_at=row[7],
    )


@router.get("", response_model=list[CircuitResponse])
async def list_circuits(
    request: Request,
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Number of rows to skip"),
) -> list[CircuitResponse]:
    """Return all circuits."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT circuit_id, circuit_name, country, locality, "
            "track_length_m, lat, lng, created_at "
            "FROM circuits ORDER BY circuit_name "
            "OFFSET :1 ROWS FETCH FIRST :2 ROWS ONLY",
            [offset, limit],
        )
        rows = await cursor.fetchall()
    return [_row_to_circuit(r) for r in rows]


@router.get("/{circuit_id}", response_model=CircuitResponse)
async def get_circuit(circuit_id: str, request: Request) -> CircuitResponse:
    """Return a single circuit by ID."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT circuit_id, circuit_name, country, locality, "
            "track_length_m, lat, lng, created_at "
            "FROM circuits WHERE circuit_id = :1",
            [circuit_id],
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Circuit {circuit_id!r} not found")
    return _row_to_circuit(row)


@router.get("/{circuit_id}/geometry")
async def get_circuit_geometry(circuit_id: str, request: Request) -> dict[str, Any]:
    """Return track geometry GeoJSON for a circuit."""
    pool = request.app.state.pool
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT track_geometry FROM circuits WHERE circuit_id = :1",
            [circuit_id],
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Circuit {circuit_id!r} not found")
    if row[0] is None:
        raise HTTPException(status_code=404, detail=f"No geometry for circuit {circuit_id!r}")
    geom = row[0] if isinstance(row[0], dict) else json.loads(str(row[0]))
    return {"circuit_id": circuit_id, "geometry": geom}
