import json

import pytest
import pytest_asyncio

from api.services.oracle import OraclePool


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = OraclePool(
        dsn="localhost:1525/FREEPDB1",
        user="f1app",
        password="f1app",
        min_connections=1,
        max_connections=4,
    )
    await p.open()

    schema_sql = open("api/db/schema.sql").read()
    await p.execute_script(schema_sql)

    yield p
    await p.close()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_insert_circuit_with_geometry(pool: OraclePool):
    """Insert a circuit with JSON track geometry and calculate distance using haversine."""
    spatial_sql = open("api/db/spatial.sql").read()
    await pool.execute_script(spatial_sql)

    # Track geometry stored as JSON array of [lng, lat] coordinate pairs
    track_geometry = json.dumps({
        "type": "LineString",
        "coordinates": [
            [9.2724, 45.6186],   # Variante del Rettifilo
            [9.2890, 45.6208],   # Curva Grande
            [9.2876, 45.6100],   # Variante Ascari
            [9.2753, 45.6126],   # Parabolica
        ],
    })

    async with pool.connection() as conn:
        cursor = conn.cursor()

        # Insert Monza with JSON-based geometry
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

        # Query: calculate distance from Milan (45.4642, 9.1900) using Haversine
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
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "monza-spatial-test"
        distance_km = float(row[2])
        # Monza is ~15-18km NE of Milan center
        assert 10 < distance_km < 25, f"Expected ~15km, got {distance_km}"


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
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


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
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
    assert result.returncode == 0, f"seed_circuits.py failed: {result.stderr}"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT COUNT(*) FROM circuits WHERE track_geometry IS NOT NULL"
        )
        row = await cursor.fetchone()
        assert row[0] >= 3, f"Expected >= 3 circuits with geometry, got {row[0]}"
