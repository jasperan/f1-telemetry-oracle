"""OpenF1 Collector — CLI entry point.

Usage:
    # Batch backfill a specific session
    python -m collectors.openf1.main --session-key 9876

    # Live polling mode during a race weekend
    python -m collectors.openf1.main --live --session-key 9876

    # Batch backfill all 2024 race sessions
    python -m collectors.openf1.main --year 2024
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from collectors.normalizer import NormalizedLap
from collectors.openf1.collector import OpenF1Collector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main(args: argparse.Namespace) -> None:
    collector = OpenF1Collector()

    if args.live:
        # Live polling mode
        if not args.session_key:
            logger.error("--session-key is required for --live mode")
            return

        async def on_laps(laps: list[NormalizedLap]) -> None:
            for lap in laps:
                logger.info(
                    "New lap: driver=%s lap=%s time=%sms tire=%s",
                    lap.driver_code,
                    lap.lap_number,
                    lap.lap_time_ms,
                    lap.tire_compound,
                )

        session = await collector.fetch_session(args.session_key)
        circuit = session.get("circuit_short_name", "")
        logger.info("Starting live poll for session %d (%s)", args.session_key, circuit)

        await collector.live_poll(
            session_key=args.session_key,
            circuit_short_name=circuit,
            callback=on_laps,
            poll_interval=args.poll_interval,
        )
    elif args.session_key:
        # Single session backfill
        result = await collector.fetch_session_backfill(args.session_key)
        laps = result["laps"]
        logger.info(
            "Backfill complete: %d laps, %d drivers with frames for session %d",
            len(laps),
            len(result["frames_by_driver"]),
            args.session_key,
        )
    elif args.year:
        # Fetch all race sessions for a year
        sessions = await collector._get_json(
            "/sessions",
            params={"year": str(args.year), "session_type": "Race"},
        )
        for sess in sessions or []:
            sk = sess["session_key"]
            circuit = sess.get("circuit_short_name", "")
            laps = await collector.fetch_laps(session_key=sk, circuit_short_name=circuit)
            logger.info("Fetched %d laps for session %d (%s)", len(laps), sk, circuit)
            await asyncio.sleep(1.0)  # rate limit
    else:
        logger.error("Specify --session-key, --year, or --live")


def cli():
    parser = argparse.ArgumentParser(description="Fetch F1 data from OpenF1 API")
    parser.add_argument("--session-key", type=int, help="OpenF1 session key to fetch")
    parser.add_argument("--year", type=int, help="Backfill all race sessions for a year")
    parser.add_argument("--live", action="store_true", help="Enable live polling mode")
    parser.add_argument(
        "--poll-interval", type=float, default=2.0, help="Seconds between live polls (default: 2.0)"
    )
    args = parser.parse_args()
    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
