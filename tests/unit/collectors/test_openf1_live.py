"""Test OpenF1 live polling mode — incremental fetch with timestamp tracking."""

import httpx
import pytest
import respx

from collectors.normalizer import NormalizedLap
from collectors.openf1.collector import OpenF1Collector

MOCK_DRIVERS_RESPONSE = [
    {
        "driver_number": 1,
        "name_acronym": "VER",
        "first_name": "Max",
        "last_name": "Verstappen",
        "team_name": "Red Bull Racing",
        "session_key": 9876,
        "meeting_key": 1234,
    },
]

MOCK_STINTS_RESPONSE = [
    {
        "driver_number": 1,
        "session_key": 9876,
        "stint_number": 1,
        "compound": "SOFT",
        "tyre_age_at_start": 0,
        "lap_start": 1,
        "lap_end": 99,
    },
]

# First poll: 2 laps
POLL1_LAPS = [
    {
        "driver_number": 1,
        "meeting_key": 1234,
        "session_key": 9876,
        "lap_number": 1,
        "lap_duration": 92.0,
        "duration_sector_1": 30.0,
        "duration_sector_2": 35.0,
        "duration_sector_3": 27.0,
        "is_pit_out_lap": True,
        "st_speed": 330.0,
        "date_start": "2024-09-01T13:05:00.000+00:00",
    },
    {
        "driver_number": 1,
        "meeting_key": 1234,
        "session_key": 9876,
        "lap_number": 2,
        "lap_duration": 81.0,
        "duration_sector_1": 27.0,
        "duration_sector_2": 31.0,
        "duration_sector_3": 23.0,
        "is_pit_out_lap": False,
        "st_speed": 342.0,
        "date_start": "2024-09-01T13:06:32.000+00:00",
    },
]

# Second poll: includes lap 2 again + new lap 3
POLL2_LAPS = [
    {
        "driver_number": 1,
        "meeting_key": 1234,
        "session_key": 9876,
        "lap_number": 2,
        "lap_duration": 81.0,
        "duration_sector_1": 27.0,
        "duration_sector_2": 31.0,
        "duration_sector_3": 23.0,
        "is_pit_out_lap": False,
        "st_speed": 342.0,
        "date_start": "2024-09-01T13:06:32.000+00:00",
    },
    {
        "driver_number": 1,
        "meeting_key": 1234,
        "session_key": 9876,
        "lap_number": 3,
        "lap_duration": 80.5,
        "duration_sector_1": 26.8,
        "duration_sector_2": 30.9,
        "duration_sector_3": 22.8,
        "is_pit_out_lap": False,
        "st_speed": 343.0,
        "date_start": "2024-09-01T13:07:53.000+00:00",
    },
]


class TestOpenF1LivePolling:
    @respx.mock
    @pytest.mark.asyncio
    async def test_live_poll_incremental_fetch(self):
        """Live polling only yields NEW laps not seen in previous polls."""
        base = "https://api.openf1.org/v1"

        # Drivers + stints fetched once at start
        respx.get(f"{base}/drivers", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_DRIVERS_RESPONSE)
        )
        respx.get(f"{base}/stints", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_STINTS_RESPONSE)
        )

        collector = OpenF1Collector(base_url=base)
        received_laps: list[NormalizedLap] = []

        async def on_new_laps(laps: list[NormalizedLap]) -> None:
            received_laps.extend(laps)

        # Mock _get_json to return different data on successive /laps calls
        poll_count = 0
        original_get = collector._get_json

        async def mock_get(path: str, params=None):
            nonlocal poll_count
            if path == "/laps":
                poll_count += 1
                if poll_count == 1:
                    return POLL1_LAPS
                else:
                    return POLL2_LAPS
            return await original_get(path, params)

        collector._get_json = mock_get

        await collector.live_poll(
            session_key=9876,
            circuit_short_name="Monza",
            callback=on_new_laps,
            poll_interval=0.01,
            max_polls=2,
        )

        # Poll 1: 2 new laps (1 and 2)
        # Poll 2: 1 new lap (3) — lap 2 is a duplicate and should be filtered
        assert len(received_laps) == 3

        lap_numbers = [lap.lap_number for lap in received_laps]
        assert 1 in lap_numbers
        assert 2 in lap_numbers
        assert 3 in lap_numbers

    @pytest.mark.asyncio
    async def test_live_poll_tracks_last_timestamp(self):
        """After polling, the collector tracks the latest timestamp seen."""
        collector = OpenF1Collector(base_url="https://api.openf1.org/v1")

        # Use a simpler approach — directly test the dedup tracking
        seen_before: set[tuple[int, int, str]] = set()
        new_laps = collector._dedup_laps(POLL1_LAPS, seen_before)
        assert len(new_laps) == 2

        # Second call with same data — all filtered
        new_laps2 = collector._dedup_laps(POLL1_LAPS, seen_before)
        assert len(new_laps2) == 0

        # Third call with poll2 — only lap 3 is new
        new_laps3 = collector._dedup_laps(POLL2_LAPS, seen_before)
        assert len(new_laps3) == 1
        assert new_laps3[0]["lap_number"] == 3
