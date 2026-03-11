"""Ergast Collector — CLI entry point.

Seeds the Oracle database with historical F1 race results from the Ergast API.

Usage:
    # Seed a single season
    python -m collectors.ergast.main --season 2024

    # Seed a range of seasons
    python -m collectors.ergast.main --from-season 2020 --to-season 2024

    # Seed specific rounds
    python -m collectors.ergast.main --season 2024 --rounds 1,5,16
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api.config import Settings
from collectors.ergast.collector import ErgastCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main(args: argparse.Namespace) -> None:
    settings = Settings()
    collector = ErgastCollector(base_url=settings.ergast_base_url)

    from_season = args.from_season or args.season
    to_season = args.to_season or args.season

    total_laps = 0
    for season in range(from_season, to_season + 1):
        if args.rounds:
            rounds = [int(r) for r in args.rounds.split(",")]
            for round_num in rounds:
                laps = await collector.fetch_race_results(season, round_num)
                total_laps += len(laps)
                logger.info("Fetched %d results for %d round %d", len(laps), season, round_num)
        else:
            laps = await collector.fetch_full_season(season)
            total_laps += len(laps)
            logger.info("Fetched %d results for season %d", len(laps), season)

    logger.info("Total: %d normalized laps across seasons %d-%d", total_laps, from_season, to_season)


def cli():
    parser = argparse.ArgumentParser(description="Fetch historical F1 data from Ergast API")
    parser.add_argument("--season", type=int, default=2024, help="Season year (default: 2024)")
    parser.add_argument("--from-season", type=int, help="Start of season range (overrides --season)")
    parser.add_argument("--to-season", type=int, help="End of season range (overrides --season)")
    parser.add_argument("--rounds", type=str, help="Comma-separated round numbers (e.g., 1,5,16)")
    args = parser.parse_args()
    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
