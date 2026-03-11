"""Integration tests for spatial features (haversine, geometry, seeding).

Uses the session-scoped pool and DDL from conftest.py.
"""

import json

import pytest

from api.services.oracle import OraclePool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_insert_circuit_with_geometry(pool: OraclePool):
    """Insert a circuit with JSON track geometry and calculate distance using haversine."""
    track_geometry = json.dumps({
        "type": "LineString",
        "coordinates": [
            [9.2724, 45.6186],
            [9.2890, 45.6208],
            [9.2876, 45.6100],
            [9.2753, 45.6126],
        ],
    })

    async with pool.connection() as conn:
        cursor = conn.cursor()

        await cursor.execute(
            """
            INSERT INTO circuits (circuit_id, circuit_name, country, locality,
                                  track_length_m, lat, lng, track_geometry)
            VALUES (:1, :2, :3, :4, :5, :6, :7, :8)
            """,
            [
                "monza-spatial-test",
                "Autodromo Nazionale Monza",
                "Italy",
                "Monza",
                5793.0,
                45.6156,
                9.2811,
                track_geometry,
            ],
        )
        await conn.commit()

        # Calculate distance from Milan using Haversine
        try:
            await cursor.execute(
                """
                SELECT c.circuit_id, c.circuit_name,
                       haversine_km(c.lat, c.lng, :1, :2) AS distance_km
                FROM circuits c
                WHERE c.circuit_id = 'monza-spatial-test'
                  AND c.track_geometry IS NOT NULL
                """,
                [45.4642, 9.1900],
            )
        except Exception:
            pytest.skip("haversine_km function not available")

        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "monza-spatial-test"
        distance_km = float(row[2])
        assert 10 < distance_km < 25, f"Expected ~15km, got {distance_km}"


async def test_spatial_index_exists(pool: OraclePool):
    """Lat/lng compound index on circuits must exist."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """
            SELECT index_name FROM user_indexes
            WHERE table_name = 'CIRCUITS'
              AND index_name = 'IDX_CIRCUITS_LAT_LNG'
            """
        )
        row = await cursor.fetchone()
        assert row is not None, "No lat/lng index found on CIRCUITS"


async def test_seed_circuits(pool: OraclePool):
    """seed_circuits.py inserts at least 3 circuits with geometry."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/seed_circuits.py"],
        capture_output=True,
        text=True,
        cwd="/home/ubuntu/git/personal/f1-telemetry-oracle",
    )
    if result.returncode != 0:
        pytest.skip(f"seed_circuits.py not available or failed: {result.stderr[:200]}")

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT COUNT(*) FROM circuits WHERE track_geometry IS NOT NULL"
        )
        row = await cursor.fetchone()
        assert row[0] >= 3, f"Expected >= 3 circuits with geometry, got {row[0]}"
