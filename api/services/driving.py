"""Driving-style twin — match a sim lap to the real driver you most resemble.

Each lap is split into three distance-based sectors; each sector's
telemetry is resampled to a fixed grid and embedded to a 384-dim vector
(the same seeded random-projection embedder as the lap pipeline). Sector
embeddings live in LAP_SECTOR_EMBEDDINGS and similarity is scored by
Oracle AI Vector Search in SQL.

Given a sim player's lap, the engine finds, per sector, the real drivers
whose sector embeddings are nearest — answering "whose driving style is
this most like, corner by corner?"
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from api.services.embeddings import LapEmbedder

logger = logging.getLogger(__name__)

SECTOR_POINTS = 50  # resample points per sector (50 * 6 channels = 300 dims -> 384)
MIN_FRAMES_PER_SECTOR = 2
MIN_TOTAL_FRAMES = 6

_embedder = LapEmbedder(n_points=SECTOR_POINTS)


def _frames_to_channels(
    frames: list[tuple],
) -> dict[str, np.ndarray]:
    """Convert telemetry frame rows to the channel dict the embedder expects.

    Frame layout (from telemetry_frames): [0]=frame_id, [1]=lap_id,
    [2]=timestamp_ms, [3]=distance_m, [4]=speed_kph, [5]=throttle_pct,
    [6]=brake_pct, [7]=steering, [8]=gear, [9]=rpm, [10]=drs.
    """
    channels = {
        "distance_m": np.array([float(f[3] or 0) for f in frames]),
        "speed_kph": np.array([float(f[4] or 0) for f in frames]),
        "throttle": np.array([float(f[5] or 0) for f in frames]),
        "brake": np.array([float(f[6] or 0) for f in frames]),
        "steering": np.array([float(f[7] or 0) for f in frames]),
        "gear": np.array([float(f[8] or 0) for f in frames]),
        "drs": np.array([float(f[10] or 0) for f in frames]),
    }
    return channels


def split_into_sectors(
    frames: list[tuple],
) -> list[dict[str, np.ndarray]]:
    """Split telemetry frames into three distance-equal sectors.

    Args:
        frames: Telemetry frame rows ordered by distance_m.

    Returns:
        List of three channel dicts (one per sector). Degenerate sectors
        (fewer than MIN_FRAMES_PER_SECTOR points) are still included but
        their embeddings will be weak.
    """
    if not frames:
        return []
    distances = [float(f[3] or 0) for f in frames]
    d_min, d_max = min(distances), max(distances)
    span = 1.0 if d_max <= d_min else d_max - d_min

    sectors: list[list[tuple]] = [[], [], []]
    for frame in frames:
        d = float(frame[3] or 0)
        idx = min(2, int((d - d_min) / span * 3))
        sectors[idx].append(frame)

    return [_frames_to_channels(s) for s in sectors]


def _vector_to_str(vec: np.ndarray) -> str:
    """Format an embedding as Oracle's vector literal string."""
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


async def _fetch_frames(pool, lap_id: str) -> list[tuple]:
    """Fetch all telemetry frames for a lap ordered by distance."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT frame_id, lap_id, timestamp_ms, distance_m, speed_kph, "
            "throttle_pct, brake_pct, steering, gear, rpm, drs "
            "FROM telemetry_frames WHERE lap_id = :1 ORDER BY distance_m",
            [lap_id],
        )
        return await cursor.fetchall()


async def embed_lap_sectors(pool, lap_id: str) -> list[np.ndarray] | None:
    """Compute and store sector embeddings for a lap.

    Args:
        pool: OraclePool.
        lap_id: Lap identifier.

    Returns:
        List of three 384-dim embeddings, or None if telemetry is too sparse.
    """
    frames = await _fetch_frames(pool, lap_id)
    if len(frames) < MIN_TOTAL_FRAMES:
        logger.info("Lap %s has only %d frames — sector embedding skipped", lap_id, len(frames))
        return None

    sectors = split_into_sectors(frames)
    if len(sectors) < 3:
        return None

    embeddings: list[np.ndarray] = []
    for sector in sectors:
        try:
            emb = _embedder.embed(sector)
        except Exception as exc:
            logger.warning("Sector embedding failed for lap %s: %s", lap_id, exc)
            return None
        # A zero-norm embedding carries no signal (all channels constant)
        # and produces NaN cosine distances — skip it.
        if np.linalg.norm(emb) < 1e-8:
            logger.info("Lap %s has a degenerate (constant) sector — skipped", lap_id)
            return None
        embeddings.append(emb)

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute("DELETE FROM lap_sector_embeddings WHERE lap_id = :1", [lap_id])
        for sector_no, emb in enumerate(embeddings, start=1):
            await cursor.execute(
                "INSERT INTO lap_sector_embeddings (lap_id, sector_no, sector_embedding) "
                "VALUES (:1, :2, :3)",
                [lap_id, sector_no, _vector_to_str(emb)],
            )
        await conn.commit()

    return embeddings


async def _ensure_candidate_embeddings(pool, sim_lap_id: str) -> None:
    """Compute sector embeddings for real laps missing them.

    Keeps the driving-twin endpoint self-sufficient on partially-seeded
    databases: any lap with enough telemetry but no sector embedding gets
    one before the similarity search runs.
    """
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """
            SELECT l.lap_id FROM laps l
            JOIN (SELECT lap_id FROM telemetry_frames
                  GROUP BY lap_id HAVING COUNT(*) >= :min_frames) f
              ON f.lap_id = l.lap_id
            LEFT JOIN lap_sector_embeddings lse ON lse.lap_id = l.lap_id
            WHERE lse.lap_id IS NULL AND l.lap_id != :sim_lap
            FETCH FIRST 50 ROWS ONLY
            """,
            {"min_frames": MIN_TOTAL_FRAMES, "sim_lap": sim_lap_id},
        )
        missing = [row[0] for row in await cursor.fetchall()]

    for lap_id in missing:
        try:
            await embed_lap_sectors(pool, lap_id)
        except Exception as exc:
            logger.warning("Backfill sector embedding failed for %s: %s", lap_id, exc)


async def driving_twin(
    pool,
    lap_id: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """Find the real driver whose driving style most resembles a lap.

    Args:
        pool: OraclePool.
        lap_id: The sim player's lap to analyze.
        top_k: Candidates considered per sector.

    Returns:
        Dict with overall_twin, per_sector matches, and the matched laps.
        Empty twin lists when there is not enough data.
    """
    sim_embeddings = await embed_lap_sectors(pool, lap_id)
    if sim_embeddings is None:
        return {
            "lap_id": lap_id,
            "error": "Not enough telemetry frames to compute sector embeddings (need >= 6)",
            "overall_twin": None,
            "sectors": [],
        }

    # Make sure candidate real laps have sector embeddings too
    await _ensure_candidate_embeddings(pool, lap_id)

    sector_results: list[dict[str, Any]] = []
    async with pool.connection() as conn:
        cursor = conn.cursor()
        for sector_no in (1, 2, 3):
            sim_emb = sim_embeddings[sector_no - 1]
            if np.linalg.norm(sim_emb) < 1e-8:
                sector_results.append({"sector": sector_no, "matches": []})
                continue
            query_vec = _vector_to_str(sim_emb)
            try:
                await cursor.execute(
                    """
                    SELECT l.lap_id, d.code, d.first_name || ' ' || d.last_name AS driver,
                           l.lap_time_ms,
                           ROUND(VECTOR_DISTANCE(lse.sector_embedding, :vec, COSINE), 4) AS similarity
                    FROM lap_sector_embeddings lse
                    JOIN laps l ON lse.lap_id = l.lap_id
                    JOIN drivers d ON l.driver_id = d.driver_id
                    WHERE lse.sector_no = :sector
                      AND lse.lap_id != :sim_lap
                      AND d.is_sim_player = 0
                      AND lse.sector_embedding IS NOT NULL
                    ORDER BY similarity
                    FETCH FIRST :k ROWS ONLY
                    """,
                    {"vec": query_vec, "sector": sector_no, "sim_lap": lap_id, "k": top_k},
                )
                columns = [desc[0].lower() for desc in cursor.description]
                rows = [dict(zip(columns, r, strict=False)) for r in await cursor.fetchall()]
            except Exception as exc:
                logger.warning("Sector %d similarity search failed: %s", sector_no, exc)
                rows = []
            sector_results.append({"sector": sector_no, "matches": rows})

    # Overall twin: the driver with the best mean similarity across sectors
    driver_scores: dict[str, list[float]] = {}
    for sector in sector_results:
        for m in sector["matches"][:1]:
            driver_scores.setdefault(m["code"], []).append(m["similarity"])
    for sector in sector_results:  # also aggregate top-k appearances
        for m in sector["matches"]:
            driver_scores.setdefault(m["code"], [])

    ranked: list[dict[str, Any]] = []
    for code, sims in driver_scores.items():
        if not sims:
            continue
        ranked.append({
            "driver_code": code,
            "mean_similarity": round(float(np.mean(sims)), 4),
            "best_sector_similarity": round(float(np.min(sims)), 4),
        })
    ranked.sort(key=lambda r: r["mean_similarity"])

    overall_twin = ranked[0] if ranked else None

    return {
        "lap_id": lap_id,
        "overall_twin": overall_twin,
        "sectors": sector_results,
        "candidates": ranked[:top_k],
    }
