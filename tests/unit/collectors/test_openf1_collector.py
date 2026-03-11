"""Test the OpenF1 collector with mocked HTTP responses (batch backfill mode)."""

import httpx
import pytest
import respx

from collectors.normalizer import NormalizedFrame, NormalizedLap
from collectors.openf1.collector import OpenF1Collector

# --- Mock OpenF1 API responses ---

MOCK_SESSIONS_RESPONSE = [
    {
        "session_key": 9876,
        "session_name": "Race",
        "session_type": "Race",
        "meeting_key": 1234,
        "date_start": "2024-09-01T13:00:00+00:00",
        "date_end": "2024-09-01T15:00:00+00:00",
        "circuit_key": 14,
        "circuit_short_name": "Monza",
        "country_name": "Italy",
        "year": 2024,
    },
]

MOCK_LAPS_RESPONSE = [
    {
        "driver_number": 1,
        "meeting_key": 1234,
        "session_key": 9876,
        "lap_number": 1,
        "lap_duration": 92.345,
        "duration_sector_1": 30.123,
        "duration_sector_2": 35.678,
        "duration_sector_3": 26.544,
        "is_pit_out_lap": True,
        "st_speed": 338.2,
        "date_start": "2024-09-01T13:05:00.000+00:00",
    },
    {
        "driver_number": 1,
        "meeting_key": 1234,
        "session_key": 9876,
        "lap_number": 2,
        "lap_duration": 81.456,
        "duration_sector_1": 27.123,
        "duration_sector_2": 31.456,
        "duration_sector_3": 22.877,
        "is_pit_out_lap": False,
        "st_speed": 342.5,
        "date_start": "2024-09-01T13:06:32.345+00:00",
    },
    {
        "driver_number": 16,
        "meeting_key": 1234,
        "session_key": 9876,
        "lap_number": 2,
        "lap_duration": 81.901,
        "duration_sector_1": 27.300,
        "duration_sector_2": 31.601,
        "duration_sector_3": 23.000,
        "is_pit_out_lap": False,
        "st_speed": 341.0,
        "date_start": "2024-09-01T13:06:33.100+00:00",
    },
]

MOCK_CAR_DATA_RESPONSE = [
    {
        "driver_number": 1,
        "session_key": 9876,
        "date": "2024-09-01T13:06:32.345+00:00",
        "speed": 320,
        "throttle": 100,
        "brake": 0,
        "n_gear": 8,
        "rpm": 12500,
        "drs": 1,
    },
    {
        "driver_number": 1,
        "session_key": 9876,
        "date": "2024-09-01T13:06:32.445+00:00",
        "speed": 322,
        "throttle": 100,
        "brake": 0,
        "n_gear": 8,
        "rpm": 12600,
        "drs": 1,
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
        "lap_end": 18,
    },
]

MOCK_DRIVERS_RESPONSE = [
    {
        "driver_number": 1,
        "broadcast_name": "M VERSTAPPEN",
        "full_name": "Max VERSTAPPEN",
        "name_acronym": "VER",
        "team_name": "Red Bull Racing",
        "team_colour": "3671C6",
        "first_name": "Max",
        "last_name": "Verstappen",
        "session_key": 9876,
        "meeting_key": 1234,
        "country_code": "NED",
    },
    {
        "driver_number": 16,
        "broadcast_name": "C LECLERC",
        "full_name": "Charles LECLERC",
        "name_acronym": "LEC",
        "team_name": "Ferrari",
        "team_colour": "E80020",
        "first_name": "Charles",
        "last_name": "Leclerc",
        "session_key": 9876,
        "meeting_key": 1234,
        "country_code": "MON",
    },
]


class TestOpenF1CollectorBatch:
    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_session(self):
        """Fetch session metadata from OpenF1."""
        base = "https://api.openf1.org/v1"

        respx.get(f"{base}/sessions", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_SESSIONS_RESPONSE)
        )

        collector = OpenF1Collector(base_url=base)
        session = await collector.fetch_session(session_key=9876)

        assert session["session_key"] == 9876
        assert session["session_type"] == "Race"
        assert session["circuit_short_name"] == "Monza"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_laps_normalizes(self):
        """Fetch laps for a session and normalize to NormalizedLap."""
        base = "https://api.openf1.org/v1"

        respx.get(f"{base}/laps", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_LAPS_RESPONSE)
        )
        respx.get(f"{base}/stints", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_STINTS_RESPONSE)
        )
        respx.get(f"{base}/drivers", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_DRIVERS_RESPONSE)
        )

        collector = OpenF1Collector(base_url=base)
        laps = await collector.fetch_laps(session_key=9876, circuit_short_name="Monza")

        assert len(laps) == 3
        assert all(isinstance(lap, NormalizedLap) for lap in laps)

        # Check VER lap 2
        ver_lap2 = [lap for lap in laps if lap.driver_code == "VER" and lap.lap_number == 2][0]
        assert ver_lap2.source == "openf1"
        assert ver_lap2.sector1_ms == 27123
        assert ver_lap2.sector2_ms == 31456
        assert ver_lap2.sector3_ms == 22877
        assert ver_lap2.lap_time_ms == 81456
        assert ver_lap2.tire_compound == "SOFT"
        assert ver_lap2.is_valid is True

        # Pit out lap should be marked invalid
        ver_lap1 = [lap for lap in laps if lap.driver_code == "VER" and lap.lap_number == 1][0]
        assert ver_lap1.is_valid is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_car_data_normalizes_frames(self):
        """Fetch car_data and produce NormalizedFrame objects."""
        base = "https://api.openf1.org/v1"

        respx.get(
            f"{base}/car_data",
            params={"session_key": "9876", "driver_number": "1"},
        ).mock(return_value=httpx.Response(200, json=MOCK_CAR_DATA_RESPONSE))

        collector = OpenF1Collector(base_url=base)
        frames = await collector.fetch_car_data(session_key=9876, driver_number=1)

        assert len(frames) == 2
        assert all(isinstance(f, NormalizedFrame) for f in frames)
        assert frames[0].speed_kph == 320
        assert frames[0].throttle_pct == 100.0
        assert frames[0].brake_pct == 0.0
        assert frames[0].gear == 8
        assert frames[0].rpm == 12500
        assert frames[0].drs == 1
        assert frames[1].speed_kph == 322

    @respx.mock
    @pytest.mark.asyncio
    async def test_rate_limit_retry(self):
        """Collector retries on HTTP 429."""
        base = "https://api.openf1.org/v1"

        route = respx.get(f"{base}/sessions", params={"session_key": "9876"})
        route.side_effect = [
            httpx.Response(429, text="Rate limited"),
            httpx.Response(200, json=MOCK_SESSIONS_RESPONSE),
        ]

        collector = OpenF1Collector(base_url=base, retry_delay=0.01)
        session = await collector.fetch_session(session_key=9876)
        assert session["session_key"] == 9876

    @respx.mock
    @pytest.mark.asyncio
    async def test_pagination_via_offset(self):
        """Collector fetches paginated results until empty page."""
        base = "https://api.openf1.org/v1"

        # Use page_size=2 so first page is full, triggering next fetch
        page1 = MOCK_LAPS_RESPONSE[:2]
        page2 = [MOCK_LAPS_RESPONSE[2]]

        respx.get(f"{base}/laps", params={"session_key": "9876", "offset": "0", "limit": "2"}).mock(
            return_value=httpx.Response(200, json=page1)
        )
        respx.get(f"{base}/laps", params={"session_key": "9876", "offset": "2", "limit": "2"}).mock(
            return_value=httpx.Response(200, json=page2)
        )

        collector = OpenF1Collector(base_url=base)
        all_data = await collector._fetch_paginated("/laps", params={"session_key": "9876"}, page_size=2)
        assert len(all_data) == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_timestamp_dedup(self):
        """Duplicate records with same driver+lap+timestamp are deduplicated."""
        base = "https://api.openf1.org/v1"

        duplicate_laps = MOCK_LAPS_RESPONSE + [MOCK_LAPS_RESPONSE[1]]  # lap 2 duplicated

        respx.get(f"{base}/laps", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=duplicate_laps)
        )
        respx.get(f"{base}/stints", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_STINTS_RESPONSE)
        )
        respx.get(f"{base}/drivers", params={"session_key": "9876"}).mock(
            return_value=httpx.Response(200, json=MOCK_DRIVERS_RESPONSE)
        )

        collector = OpenF1Collector(base_url=base)
        laps = await collector.fetch_laps(session_key=9876, circuit_short_name="Monza")

        # Should be 3, not 4 — duplicate removed
        assert len(laps) == 3
