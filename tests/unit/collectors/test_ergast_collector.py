"""Test the Ergast historical collector with mocked HTTP responses."""

import httpx
import pytest
import respx

from collectors.ergast.collector import ErgastCollector
from collectors.normalizer import NormalizedLap

# A realistic Ergast API response for 2024 Italian GP results
MOCK_ERGAST_RESPONSE = {
    "MRData": {
        "xmlns": "http://ergast.com/mrd/1.5",
        "series": "f1",
        "limit": "30",
        "offset": "0",
        "total": "20",
        "RaceTable": {
            "season": "2024",
            "round": "16",
            "Races": [
                {
                    "season": "2024",
                    "round": "16",
                    "url": "https://en.wikipedia.org/wiki/2024_Italian_Grand_Prix",
                    "raceName": "Italian Grand Prix",
                    "Circuit": {
                        "circuitId": "monza",
                        "url": "http://en.wikipedia.org/wiki/Autodromo_Nazionale_Monza",
                        "circuitName": "Autodromo Nazionale Monza",
                        "Location": {
                            "lat": "45.6156",
                            "long": "9.2811",
                            "locality": "Monza",
                            "country": "Italy",
                        },
                    },
                    "date": "2024-09-01",
                    "Results": [
                        {
                            "number": "16",
                            "position": "1",
                            "positionText": "1",
                            "points": "25",
                            "Driver": {
                                "driverId": "leclerc",
                                "permanentNumber": "16",
                                "code": "LEC",
                                "url": "http://en.wikipedia.org/wiki/Charles_Leclerc",
                                "givenName": "Charles",
                                "familyName": "Leclerc",
                                "dateOfBirth": "1997-10-16",
                                "nationality": "Monegasque",
                            },
                            "Constructor": {
                                "constructorId": "ferrari",
                                "url": "http://en.wikipedia.org/wiki/Scuderia_Ferrari",
                                "name": "Ferrari",
                                "nationality": "Italian",
                            },
                            "grid": "4",
                            "laps": "53",
                            "status": "Finished",
                            "Time": {"millis": "4576234", "time": "1:14:40.727"},
                            "FastestLap": {
                                "rank": "2",
                                "lap": "48",
                                "Time": {"time": "1:22.856"},
                                "AverageSpeed": {"units": "kph", "speed": "251.939"},
                            },
                        },
                        {
                            "number": "81",
                            "position": "2",
                            "positionText": "2",
                            "points": "18",
                            "Driver": {
                                "driverId": "piastri",
                                "permanentNumber": "81",
                                "code": "PIA",
                                "url": "http://en.wikipedia.org/wiki/Oscar_Piastri",
                                "givenName": "Oscar",
                                "familyName": "Piastri",
                                "dateOfBirth": "2001-04-06",
                                "nationality": "Australian",
                            },
                            "Constructor": {
                                "constructorId": "mclaren",
                                "url": "http://en.wikipedia.org/wiki/McLaren",
                                "name": "McLaren",
                                "nationality": "British",
                            },
                            "grid": "2",
                            "laps": "53",
                            "status": "Finished",
                            "Time": {"millis": "4578962", "time": "+2.728"},
                            "FastestLap": {
                                "rank": "1",
                                "lap": "51",
                                "Time": {"time": "1:22.416"},
                                "AverageSpeed": {"units": "kph", "speed": "253.283"},
                            },
                        },
                    ],
                }
            ],
        },
    }
}


MOCK_SCHEDULE_RESPONSE = {
    "MRData": {
        "RaceTable": {
            "season": "2024",
            "Races": [
                {
                    "season": "2024",
                    "round": "16",
                    "raceName": "Italian Grand Prix",
                    "Circuit": {
                        "circuitId": "monza",
                        "circuitName": "Autodromo Nazionale Monza",
                        "Location": {"lat": "45.6156", "long": "9.2811", "locality": "Monza", "country": "Italy"},
                    },
                    "date": "2024-09-01",
                },
            ],
        }
    }
}


class TestErgastCollector:
    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_race_results(self):
        """Fetch results for a specific race and get NormalizedLap list."""
        base_url = "https://ergast.com/api/f1"

        respx.get(f"{base_url}/2024/16/results.json").mock(
            return_value=httpx.Response(200, json=MOCK_ERGAST_RESPONSE)
        )

        collector = ErgastCollector(base_url=base_url)
        laps = await collector.fetch_race_results(season=2024, round_num=16)

        assert len(laps) == 2
        assert all(isinstance(lap, NormalizedLap) for lap in laps)

        # First result: Leclerc
        leclerc = laps[0]
        assert leclerc.driver_id == "leclerc"
        assert leclerc.driver_code == "LEC"
        assert leclerc.circuit_id == "monza"
        assert leclerc.position == 1
        assert leclerc.source == "ergast"
        assert leclerc.season == 2024
        assert leclerc.round_number == 16
        assert leclerc.team_name == "Ferrari"
        # 1:22.856 = 82856ms
        assert leclerc.lap_time_ms == 82856

        # Second result: Piastri
        piastri = laps[1]
        assert piastri.driver_id == "piastri"
        assert piastri.driver_code == "PIA"
        assert piastri.position == 2
        assert piastri.team_name == "McLaren"
        # 1:22.416 = 82416ms
        assert piastri.lap_time_ms == 82416

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_season_schedule(self):
        """Fetch the race calendar for a season."""
        base_url = "https://ergast.com/api/f1"

        respx.get(f"{base_url}/2024.json").mock(
            return_value=httpx.Response(200, json=MOCK_SCHEDULE_RESPONSE)
        )

        collector = ErgastCollector(base_url=base_url)
        races = await collector.fetch_season_schedule(season=2024)

        assert len(races) == 1
        assert races[0]["round"] == "16"
        assert races[0]["Circuit"]["circuitId"] == "monza"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_handles_empty_results(self):
        """When no results are available, return an empty list."""
        base_url = "https://ergast.com/api/f1"

        empty_response = {
            "MRData": {
                "RaceTable": {
                    "season": "2024",
                    "round": "99",
                    "Races": [],
                }
            }
        }
        respx.get(f"{base_url}/2024/99/results.json").mock(
            return_value=httpx.Response(200, json=empty_response)
        )

        collector = ErgastCollector(base_url=base_url)
        laps = await collector.fetch_race_results(season=2024, round_num=99)
        assert laps == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_retries_on_429(self):
        """Collector retries on HTTP 429 (rate limit)."""
        base_url = "https://ergast.com/api/f1"

        route = respx.get(f"{base_url}/2024/16/results.json")
        route.side_effect = [
            httpx.Response(429, text="Rate limited"),
            httpx.Response(200, json=MOCK_ERGAST_RESPONSE),
        ]

        collector = ErgastCollector(base_url=base_url, retry_delay=0.01)
        laps = await collector.fetch_race_results(season=2024, round_num=16)
        assert len(laps) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_circuits_from_results(self):
        """Collector extracts circuit metadata from race results."""
        base_url = "https://ergast.com/api/f1"

        respx.get(f"{base_url}/2024/16/results.json").mock(
            return_value=httpx.Response(200, json=MOCK_ERGAST_RESPONSE)
        )

        collector = ErgastCollector(base_url=base_url)
        laps = await collector.fetch_race_results(season=2024, round_num=16)

        # All laps from this race should reference the same circuit
        assert all(lap.circuit_id == "monza" for lap in laps)
