"""Seed the CIRCUITS table with real F1 track data and simplified geometry.

Geometry data: simplified polylines from official track maps (WGS84).
Each circuit has 4-8 coordinate pairs tracing the major corners,
stored as GeoJSON-like LineString in the track_geometry JSON column.

Usage:
    python scripts/seed_circuits.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oracledb

from api.config import Settings

# Each circuit: (circuit_id, name, country, locality, track_length_m, lat, lng, coordinates)
# coordinates = [[lng1, lat1], [lng2, lat2], ...] — WGS84 lon/lat pairs
CIRCUITS = [
    {
        "circuit_id": "monza",
        "circuit_name": "Autodromo Nazionale Monza",
        "country": "Italy",
        "locality": "Monza",
        "track_length_m": 5793.0,
        "lat": 45.6156,
        "lng": 9.2811,
        "coordinates": [
            [9.2724, 45.6186],   # Variante del Rettifilo
            [9.2809, 45.6213],   # Curva Grande approach
            [9.2890, 45.6208],   # Curva Grande exit
            [9.2899, 45.6150],   # Lesmo 1
            [9.2876, 45.6100],   # Variante Ascari
            [9.2811, 45.6097],   # Curve di Ascari exit
            [9.2753, 45.6126],   # Parabolica entry
            [9.2724, 45.6156],   # Parabolica exit (back to start)
        ],
    },
    {
        "circuit_id": "silverstone",
        "circuit_name": "Silverstone Circuit",
        "country": "UK",
        "locality": "Silverstone",
        "track_length_m": 5891.0,
        "lat": 52.0786,
        "lng": -1.0169,
        "coordinates": [
            [-1.0146, 52.0786],  # Abbey
            [-1.0096, 52.0740],  # Farm
            [-1.0130, 52.0695],  # Village / The Loop
            [-1.0188, 52.0700],  # Aintree
            [-1.0245, 52.0735],  # Brooklands
            [-1.0268, 52.0775],  # Copse
            [-1.0230, 52.0806],  # Maggotts / Becketts
            [-1.0146, 52.0786],  # Hangar Straight back to Abbey
        ],
    },
    {
        "circuit_id": "spa",
        "circuit_name": "Circuit de Spa-Francorchamps",
        "country": "Belgium",
        "locality": "Spa",
        "track_length_m": 7004.0,
        "lat": 50.4372,
        "lng": 5.9714,
        "coordinates": [
            [5.9714, 50.4372],   # La Source
            [5.9763, 50.4367],   # Eau Rouge approach
            [5.9785, 50.4380],   # Raidillon
            [5.9896, 50.4424],   # Les Combes
            [5.9940, 50.4380],   # Malmedy / Rivage
            [5.9830, 50.4320],   # Pouhon
            [5.9714, 50.4335],   # Stavelot
            [5.9680, 50.4350],   # Blanchimont
            [5.9714, 50.4372],   # Bus Stop back to La Source
        ],
    },
    {
        "circuit_id": "suzuka",
        "circuit_name": "Suzuka International Racing Course",
        "country": "Japan",
        "locality": "Suzuka",
        "track_length_m": 5807.0,
        "lat": 34.8431,
        "lng": 136.5407,
        "coordinates": [
            [136.5407, 34.8431],  # Start/Finish
            [136.5380, 34.8458],  # First curve
            [136.5348, 34.8470],  # S-curves
            [136.5330, 34.8440],  # Dunlop curve
            [136.5370, 34.8410],  # Degner curves
            [136.5410, 34.8395],  # Hairpin
            [136.5440, 34.8415],  # Spoon curve
            [136.5430, 34.8440],  # 130R
            [136.5407, 34.8431],  # Casio Triangle back to start
        ],
    },
    {
        "circuit_id": "jeddah",
        "circuit_name": "Jeddah Corniche Circuit",
        "country": "Saudi Arabia",
        "locality": "Jeddah",
        "track_length_m": 6174.0,
        "lat": 21.6319,
        "lng": 39.1044,
        "coordinates": [
            [39.1044, 21.6319],  # Start/Finish
            [39.1060, 21.6340],  # Turn 1-3
            [39.1080, 21.6375],  # Turn 4-6
            [39.1100, 21.6350],  # Turn 13 (fast kink)
            [39.1075, 21.6310],  # Turn 22-25
            [39.1050, 21.6300],  # Turn 27 (final corner)
            [39.1044, 21.6319],  # Back to start
        ],
    },
]


async def seed():
    settings = Settings()
    pool = oracledb.create_pool_async(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=settings.oracle_dsn,
        min=1,
        max=2,
    )

    conn = await pool.acquire()
    cursor = conn.cursor()

    inserted = 0
    for c in CIRCUITS:
        # Check if already exists
        await cursor.execute(
            "SELECT COUNT(*) FROM circuits WHERE circuit_id = :1",
            [c["circuit_id"]],
        )
        row = await cursor.fetchone()
        if row[0] > 0:
            continue

        # Build GeoJSON-like geometry
        geometry = json.dumps({
            "type": "LineString",
            "coordinates": c["coordinates"],
        })

        await cursor.execute(
            """
            INSERT INTO circuits (circuit_id, circuit_name, country, locality,
                                  track_length_m, lat, lng, track_geometry)
            VALUES (:cid, :cname, :country, :locality, :length, :lat, :lng, :geom)
            """,
            {
                "cid": c["circuit_id"],
                "cname": c["circuit_name"],
                "country": c["country"],
                "locality": c["locality"],
                "length": c["track_length_m"],
                "lat": c["lat"],
                "lng": c["lng"],
                "geom": geometry,
            },
        )
        inserted += 1

    await conn.commit()
    await pool.release(conn)
    await pool.close(force=True)

    print(f"Seeded {inserted} circuits ({len(CIRCUITS)} total, skipped existing)")


if __name__ == "__main__":
    asyncio.run(seed())
