"""Seed the RAG text knowledge base with in-database embeddings.

Inserts a curated corpus of race-engineering knowledge (strategy notes,
setup guides, circuit guides, race-craft) into RACE_DOCUMENTS. Each
document is embedded *inside Oracle* with VECTOR_EMBEDDING() — the
ALL_MINILM_L12_V2 ONNX model runs in the database, so no Python-side
embedding call is made.

Usage:
    python -m scripts.seed_race_documents
    python -m scripts.seed_race_documents --drop

The script is idempotent: existing doc_ids are left untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Knowledge corpus: (doc_id, doc_type, title, content)
# ---------------------------------------------------------------------------
DOCUMENTS: list[tuple[str, str, str, str]] = [
    # --- Tire strategy ------------------------------------------------------
    (
        "strat_compounds",
        "strategy",
        "Tire compound characteristics",
        "Formula 1 uses five dry/wet tire compounds per weekend. Soft tires offer the most peak grip "
        "but degrade fastest (roughly 25 lap life); Mediums balance pace and durability (~35 laps); "
        "Hards are the most durable (~45 laps) but up to 0.6s per lap slower in qualifying trim. "
        "Intermediates suit light rain and damp tracks, full wets suit standing water. In the race, "
        "undercutting — pitting one lap before a rival — can pass them if your out-lap is strong and "
        "the pit lane delta is under ~25 seconds.",
    ),
    (
        "strat_pit_window",
        "strategy",
        "Pit window fundamentals",
        "The optimal pit window depends on tire cliff, traffic, and safety car timing. Pitting early "
        "avoids heavy degradation but leaves you vulnerable to an undercut; pitting late preserves "
        "track position. A rule of thumb: stop when your tire grip falls below 50% or when a safety "
        "car compresses the field — a free pit stop under SC can be worth 15-20 seconds. Fresh tires "
        "are typically 1.5-2.5s per lap faster than tires past their cliff, but you lose 20-25 seconds "
        "in the pit lane.",
    ),
    (
        "strat_deg",
        "strategy",
        "Tire degradation physics",
        "Tire degradation accelerates with track temperature, fuel load, and sliding. Grip loss per "
        "lap rises roughly 15% per 10°C of track temperature above 30°C, and high-fuel running "
        "increases lateral load on the rears. Degradation is not linear: tires plateau near peak grip "
        "for the first third of their life, then fall off an exponential cliff. Managing brake "
        "temperature and avoiding wheelspin on exit preserves the rears late in a stint.",
    ),
    # --- Setup --------------------------------------------------------------
    (
        "setup_wing",
        "setup",
        "Front and rear wing balance",
        "Adding front wing increases front grip and turn-in but adds drag and can cause understeer "
        "mid-corner if the rear is too stiff. Adding rear wing adds rear grip and stability under "
        "braking and through high-speed corners at the cost of straight-line speed. If the car "
        "understeers on entry, increase front wing or soften the front anti-roll bar; if it "
        "oversteers on exit, add rear wing or soften the rear springs.",
    ),
    (
        "setup_mech",
        "setup",
        "Mechanical grip: camber, toe, ride height",
        "Negative camber increases cornering grip by keeping more tire contact patch on the track, "
        "but excessive camber overheats the inside shoulder. Toe-out on the front improves turn-in "
        "but hurts straight-line stability; toe-in on the rear improves stability under braking. "
        "Lowering ride height reduces drag and lowers the center of gravity but risks bottoming "
        "out; if you are bottoming, raise it by 2-3 clicks before changing springs.",
    ),
    (
        "setup_diff",
        "setup",
        "Differential and brake bias",
        "A higher differential on-throttle locking helps traction out of slow corners but causes "
        "understeer on power. Brake bias further forward increases stability under heavy braking "
        "but can lock the fronts and extend braking distance; bias further rearward rotates the car "
        "on entry but risks rear instability. On a dry track, most drivers run 55-58% front bias.",
    ),
    # --- Circuit guides -----------------------------------------------------
    (
        "circuit_monza",
        "circuit_guide",
        "Monza — Temple of Speed",
        "Monza is the fastest track on the calendar with long straights and four chicanes. "
        "Run minimum downforce for top speed; the car must be stable under braking into the "
        "first and second chicanes. Curva Grande is flat-out, and the Lesmos reward a balanced "
        "car. The Ascari chicane requires precise kerb usage; exit speed onto the main straight "
        "is worth more than entry speed through Ascari.",
    ),
    (
        "circuit_silverstone",
        "circuit_guide",
        "Silverstone — high-speed sweepers",
        "Silverstone is a high-downforce track dominated by fast corners: Copse (flat-out in a "
        "modern car), Maggotts-Becketts-Chapel, Stowe, and the new-look Abbey. Rear stability "
        "through Maggotts is critical — a snap of oversteer there ruins the lap. Kerb riding "
        "through the Village-Loop complex and Wellington straight is essential for lap time.",
    ),
    (
        "circuit_singapore",
        "circuit_guide",
        "Singapore — Marina Bay street circuit",
        "Marina Bay is a high-downforce street circuit with 19 corners, tight walls, and bumpy "
        "surface. Ride quality and mechanical grip matter more than aero efficiency. Traction "
        "out of Turns 13-16 is the biggest lap-time differentiator. Under-slung ride height "
        "risks bottoming on the bumps; drivers typically run the softest suspension available.",
    ),
    # --- Race craft ---------------------------------------------------------
    (
        "craft_drs",
        "racecraft",
        "DRS and overtaking",
        "DRS is active only in designated zones when within one second of the car ahead at the "
        "detection point. Deploying DRS on a straight can be worth 0.3-0.6s per lap. To overtake "
        "with DRS, position your car on the racing line before the zone ends and brake later "
        "but smoother to avoid running wide. Defend by taking the inside line into the corner "
        "before the DRS detection point.",
    ),
    (
        "craft_fuel",
        "racecraft",
        "Fuel management",
        "Fuel saving is achieved by lifting and coasting earlier, short-shifting, and running "
        "lower engine modes on straights. Every 10kg of fuel saved is worth roughly 0.3s per lap. "
        "Lift-and-coast is most effective on medium and high-speed corners; avoid heavy braking "
        "that wastes energy. In a fuel-critical race, plan 1-2 laps of lift-and-coast per stint "
        "rather than running out of fuel late.",
    ),
    (
        "craft_race_start",
        "racecraft",
        "Race starts and launches",
        "A good launch balances wheelspin against bogging down. Build revs to the recommended "
        "launch RPM, release the clutch smoothly, and modulate throttle to keep wheelspin under "
        "10%. On the first lap, tires are cold and grip is low — brake earlier and smoother. "
        "The first lap accounts for most overtakes in a race, but also most first-corner "
        "incidents; risk is highest when the field bunches.",
    ),
    # --- Real-world F1 knowledge -------------------------------------------
    (
        "hist_2023",
        "historical",
        "2023 F1 season",
        "Max Verstappen and Red Bull dominated 2023, winning 19 of 22 races. Verstappen set "
        "records for most wins in a season (19) and most consecutive wins (10, from Miami to "
        "Monza). Red Bull won 21 of 22 races. The season featured Sprint weekends in Baku, "
        "Austria, Belgium, Qatar, and Austin. Qatar hosted the first sprint-race weekend with "
        "mandatory pit stops due to tire wear concerns.",
    ),
    (
        "hist_2024",
        "historical",
        "2024 F1 season",
        "2024 was a four-way title fight: Verstappen (Red Bull), Norris (McLaren), Leclerc and "
        "Sainz (Ferrari). Verstappen won his fourth consecutive drivers' title at the Las Vegas "
        "GP. McLaren won the constructors' championship, their first since 1998. The season "
        "opened in Bahrain and ended in Abu Dhabi with 24 races — the longest calendar ever.",
    ),
    (
        "driver_verstappen",
        "historical",
        "Verstappen driving style",
        "Verstappen's style features late, aggressive braking and rotation with the steering "
        "wheel, carrying more speed into corners than most and managing oversteer on exit. He is "
        "known for exceptional car control at the limit and strong tire management, especially "
        "on the front-left at tracks like Bahrain and Silverstone. His qualifying laps are "
        "built on committed, over-rotated entries with early throttle application.",
    ),
    (
        "driver_hamilton",
        "historical",
        "Hamilton driving style",
        "Hamilton is renowned for smooth inputs, precise trail-braking, and gentle throttle "
        "application that preserves rear tires. He favors a stable rear and uses the brake to "
        "rotate the car rather than the steering wheel. In wet conditions he is considered the "
        "benchmark, reading grip levels early and building confidence through the field.",
    ),
    (
        "driver_alonso",
        "historical",
        "Alonso driving style",
        "Alonso combines aggressive braking with excellent rear stability and racecraft. He is "
        "famous for passing drivers with moves that rely on late braking and forcing rivals to "
        "cover the inside. His tire management is among the best on the grid, regularly "
        "extending stints beyond expectation.",
    ),
    (
        "driver_norris",
        "historical",
        "Norris driving style",
        "Norris is precise and smooth with strong one-lap pace, often extracting more from "
        "the tires in qualifying than expected. He is measured in races, avoiding risky moves "
        "and capitalizing on others' mistakes. His consistency and feedback to engineers make "
        "him a strong development driver.",
    ),
]


async def seed(pool) -> int:
    """Insert the corpus with in-database embeddings.

    Args:
        pool: OraclePool instance.

    Returns:
        Number of documents inserted.
    """
    inserted = 0
    async with pool.connection() as conn:
        cursor = conn.cursor()
        for doc_id, doc_type, title, content in DOCUMENTS:
            try:
                await cursor.execute(
                    """
                    INSERT INTO race_documents (doc_id, doc_type, title, content, content_embedding)
                    VALUES (
                        :doc_id,
                        :doc_type,
                        :title,
                        :content,
                        VECTOR_EMBEDDING(ALL_MINILM_L12_V2 USING :content AS DATA)
                    )
                    """,
                    {
                        "doc_id": doc_id,
                        "doc_type": doc_type,
                        "title": title,
                        "content": content,
                    },
                )
                inserted += 1
            except Exception as exc:
                # ORA-00001 = duplicate doc_id -> skip
                err = getattr(exc, "args", [None])[0]
                if hasattr(err, "code") and err.code == 1:
                    continue
                raise
        await conn.commit()
    return inserted


async def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Seed RAG knowledge base with in-database embeddings")
    parser.add_argument("--drop", action="store_true", help="Drop all race_documents before seeding")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from api.config import Settings
    from api.services.onnx import model_exists
    from api.services.oracle import OraclePool

    settings = Settings()

    pool = OraclePool(
        dsn=settings.oracle_dsn,
        user=settings.oracle_user,
        password=settings.oracle_password,
    )
    await pool.open()

    try:
        if not await model_exists(pool, "ALL_MINILM_L12_V2"):
            logger.warning("Embedding model not loaded — run: python -m scripts.load_onnx_models")
            return

        if args.drop:
            async with pool.connection() as conn:
                cursor = conn.cursor()
                await cursor.execute("DELETE FROM race_documents")
                await conn.commit()
            logger.info("Dropped all race_documents")

        inserted = await seed(pool)
        logger.info("Seeded %d race documents (skipped existing)", inserted)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
