"""F1 24 UDP Collector — CLI entry point.

Listens for F1 24 game UDP telemetry on port 20777 and prints to console.

Usage:
    # Listen with default settings
    python -m collectors.f1_udp.main

    # Custom port and host
    python -m collectors.f1_udp.main --host 0.0.0.0 --port 20777
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from collectors.f1_udp.listener import F1UDPListener
from collectors.normalizer import NormalizedFrame, NormalizedLap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Counters for logging
_lap_count = 0
_frame_count = 0


async def main(args: argparse.Namespace) -> None:
    async def on_lap(lap: NormalizedLap) -> None:
        global _lap_count
        _lap_count += 1
        logger.info(
            "Lap %d | Driver: %s | Time: %sms | Tire: %s (age %s) | Fuel: %skg",
            lap.lap_number,
            lap.driver_id,
            lap.lap_time_ms,
            lap.tire_compound,
            lap.tire_age_laps,
            lap.fuel_load_kg,
        )

    async def on_frame(frame: NormalizedFrame) -> None:
        global _frame_count
        _frame_count += 1
        if _frame_count % 100 == 0:
            logger.info(
                "Frame #%d | Speed: %.0f kph | Throttle: %.0f%% | Brake: %.0f%% | Gear: %d",
                _frame_count,
                frame.speed_kph,
                frame.throttle_pct,
                frame.brake_pct,
                frame.gear,
            )

    listener = F1UDPListener(
        host=args.host,
        port=args.port,
        on_lap=on_lap,
        on_frame=on_frame,
    )

    transport, port = await listener.start()
    logger.info("Listening for F1 24 UDP on %s:%d", args.host, port)

    try:
        # Run until interrupted
        while True:
            await asyncio.sleep(10)
            logger.info("Stats: %d laps, %d frames received", _lap_count, _frame_count)
    except asyncio.CancelledError:
        pass
    finally:
        listener.stop()


def cli():
    parser = argparse.ArgumentParser(description="F1 24 UDP telemetry collector")
    parser.add_argument("--host", default="0.0.0.0", help="UDP bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=20777, help="UDP port (default: 20777)")
    args = parser.parse_args()
    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
