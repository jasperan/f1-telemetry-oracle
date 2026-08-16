"""Integration tests — text RAG and the driving-style twin.

Exercises the in-database embedding pipeline end to end:
  * inserting documents embedded by VECTOR_EMBEDDING() in SQL
  * semantic retrieval over race_documents
  * per-sector driving-style matching over lap_sector_embeddings
"""

from __future__ import annotations

import math
import uuid

import pytest

from api.services import driving
from api.services.onnx import MODEL_EMBEDDING, embed_text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_insert_and_search_document(pool):
    """A document embedded in-database is found by a semantically related query."""
    doc_id = f"it-doc-{uuid.uuid4().hex[:8]}"
    content = (
        "Brake bias further rearward rotates the car on entry but risks rear "
        "instability. On a dry track most drivers run 55-58% front bias."
    )
    q = "how should I set my brake bias for stability?"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """
            INSERT INTO race_documents (doc_id, doc_type, title, content, content_embedding)
            VALUES (:doc_id, 'setup', :title, :content,
                    VECTOR_EMBEDDING(ALL_MINILM_L12_V2 USING :content AS DATA))
            """,
            {"doc_id": doc_id, "title": "Brake bias", "content": content},
        )
        await conn.commit()

    # Semantic search from Python-side embedding of the query
    query_vec = await embed_text(pool, MODEL_EMBEDDING, q)
    assert query_vec is not None
    vec_str = "[" + ",".join(f"{v:.6f}" for v in query_vec) + "]"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """
            SELECT doc_id, VECTOR_DISTANCE(content_embedding, :1, COSINE) AS sim
            FROM race_documents
            WHERE content_embedding IS NOT NULL
            ORDER BY sim
            FETCH FIRST 10 ROWS ONLY
            """,
            [vec_str],
        )
        rows = await cursor.fetchall()

    doc_ids = [r[0] for r in rows]
    assert doc_id in doc_ids, "Newly inserted brake-bias doc should rank near the top"


def _make_style_frames(code: str, n: int = 90) -> list[tuple]:
    """Three distinct driving styles with per-sector variation everywhere.

    STA = sharp early braking, narrow steering. STB = smooth trailing
    braking, wide steering. STS (sim) = a genuine blend: STA-style sharp
    braking with STB-style wide steering — so per-sector cosine similarity
    lands strictly between the two and the ranking is meaningful.
    """
    frames = []
    for i in range(n):
        progress = i / n
        if code == "STA":
            brake = 100 if 0.22 < progress < 0.30 else 0
            steer_amp = 0.3
        elif code == "STB":
            brake = (
                max(0.0, 100 * (1 - abs(progress - 0.30) / 0.12)) if progress < 0.5 else 0
            )
            steer_amp = 0.6
        else:  # STS — sim lap: blend of A braking and B steering
            brake = 100 if 0.22 < progress < 0.30 else 0
            steer_amp = 0.6
        speed = round(300 + 60 * math.sin(progress * 4.0) - brake * 1.2, 1)
        throttle = round(100 - brake + 8 * math.sin(progress * 3.0), 2)
        steering = round(0.5 * math.sin(progress * 6.0) * steer_amp, 4)
        frames.append(
            (
                f"{code}_f{i}",
                f"twin_{code}",
                i * 500,
                round(progress * 5000, 2),
                speed,
                throttle,
                round(brake, 2),
                steering,
                min(8, max(1, int(speed / 40))),
                9000 + i,
                0,
            )
        )
    return frames


async def test_driving_twin_end_to_end(pool):
    """Sim lap is matched against real-style laps per sector."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        # Base circuit/session from the fixture, plus style laps
        for code, full_id, is_sim in [
            ("STA", "STYLEA", False),
            ("STB", "STYLEB", False),
            ("STS", "STYLESIM", True),
        ]:
            await cursor.execute(
                "SELECT COUNT(*) FROM drivers WHERE driver_id = :1", [full_id]
            )
            if (await cursor.fetchone())[0] == 0:
                await cursor.execute(
                    "INSERT INTO drivers (driver_id, code, first_name, last_name, "
                    "driver_number, nationality, is_sim_player) "
                    "VALUES (:1, :2, 'Style', 'Driver', 50, 'INT', :3)",
                    [full_id, code, 1 if is_sim else 0],
                )
            lap_id = f"twin_{code}"
            await cursor.execute("DELETE FROM telemetry_frames WHERE lap_id = :1", [lap_id])
            await cursor.execute("DELETE FROM lap_sector_embeddings WHERE lap_id = :1", [lap_id])
            await cursor.execute("DELETE FROM laps WHERE lap_id = :1", [lap_id])
            await cursor.execute(
                "INSERT INTO laps (lap_id, session_id, driver_id, lap_number, lap_time_ms, "
                "tire_compound, tire_age_laps) VALUES (:1, 'monza_2024_r', :2, 3, 86000, 'SOFT', 2)",
                [lap_id, full_id],
            )
            for f in _make_style_frames(code):
                await cursor.execute(
                    "INSERT INTO telemetry_frames (frame_id, lap_id, timestamp_ms, distance_m, "
                    "speed_kph, throttle_pct, brake_pct, steering, gear, rpm, drs) "
                    "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11)",
                    list(f),
                )
        await conn.commit()

    # The sim lap is deliberately a blend of STYLEA (braking) and STYLEB (throttle)
    result = await driving.driving_twin(pool, "twin_STS", top_k=3)
    assert "error" not in result, result.get("error")
    assert result["overall_twin"] is not None
    assert result["overall_twin"]["driver_code"] in ("STA", "STB")
    assert len(result["sectors"]) == 3
    for sector in result["sectors"]:
        assert sector["matches"], "Every sector should have at least one match"
