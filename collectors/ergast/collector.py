"""Ergast Historical F1 Data Collector.

Fetches historical race results, schedules, and driver/circuit metadata from the
Ergast API (https://ergast.com/api/f1/) and normalizes them to NormalizedLap objects
for Oracle DB insertion.

Covers seasons 1950-2025 (~1100 races, ~26000 results).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from collectors.normalizer import NormalizedLap, normalize_ergast_result

logger = logging.getLogger(__name__)


class ErgastCollector:
    """Async collector for the Ergast F1 API."""

    def __init__(
        self,
        base_url: str = "https://ergast.com/api/f1",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._timeout = timeout

    async def _get_json(self, path: str) -> dict[str, Any]:
        """Make a GET request with retry on 429 / 5xx.

        Args:
            path: URL path relative to base_url (e.g., "/2024/16/results.json")

        Returns:
            Parsed JSON response body

        Raises:
            httpx.HTTPStatusError: After exhausting retries on non-retryable errors
        """
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(self._max_retries):
                try:
                    response = await client.get(url)

                    if response.status_code == 429:
                        delay = self._retry_delay * (2 ** attempt)
                        logger.warning(
                            "Rate limited (429) on %s, retry %d/%d in %.1fs",
                            url, attempt + 1, self._max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    if response.status_code >= 500:
                        delay = self._retry_delay * (2 ** attempt)
                        logger.warning(
                            "Server error (%d) on %s, retry %d/%d in %.1fs",
                            response.status_code, url, attempt + 1, self._max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    response.raise_for_status()
                    return response.json()

                except httpx.TimeoutException as exc:
                    last_exc = exc
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning(
                        "Timeout on %s, retry %d/%d in %.1fs",
                        url, attempt + 1, self._max_retries, delay,
                    )
                    await asyncio.sleep(delay)

        if last_exc:
            raise last_exc
        raise httpx.HTTPStatusError(
            f"Failed after {self._max_retries} retries",
            request=httpx.Request("GET", url),
            response=httpx.Response(500),
        )

    async def fetch_season_schedule(self, season: int) -> list[dict[str, Any]]:
        """Fetch the race calendar for a given season.

        Args:
            season: Year (e.g., 2024)

        Returns:
            List of race dicts from the Ergast RaceTable
        """
        data = await self._get_json(f"/{season}.json")
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return races

    async def fetch_race_results(self, season: int, round_num: int) -> list[NormalizedLap]:
        """Fetch race results for a specific Grand Prix and normalize them.

        Args:
            season: Year (e.g., 2024)
            round_num: Round number in the season (e.g., 16)

        Returns:
            List of NormalizedLap, one per driver who finished/classified
        """
        data = await self._get_json(f"/{season}/{round_num}/results.json")

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if not races:
            logger.info("No race data for %d round %d", season, round_num)
            return []

        race = races[0]
        results = race.get("Results", [])
        laps: list[NormalizedLap] = []

        for idx, result in enumerate(results):
            try:
                lap = normalize_ergast_result(race, driver_index=idx)
                laps.append(lap)
            except (KeyError, ValueError, IndexError) as exc:
                logger.warning(
                    "Failed to normalize result %d for %d/%d: %s",
                    idx, season, round_num, exc,
                )

        logger.info(
            "Fetched %d results for %d round %d (%s)",
            len(laps), season, round_num, race.get("raceName", "?"),
        )
        return laps

    async def fetch_qualifying_results(self, season: int, round_num: int) -> list[NormalizedLap]:
        """Fetch qualifying results for a specific Grand Prix and normalize them.

        Args:
            season: Year (e.g., 2024)
            round_num: Round number in the season (e.g., 16)

        Returns:
            List of NormalizedLap, one per driver who set a qualifying time
        """
        data = await self._get_json(f"/{season}/{round_num}/qualifying.json")

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if not races:
            logger.info("No qualifying data for %d round %d", season, round_num)
            return []

        race = races[0]
        qualifying_results = race.get("QualifyingResults", [])
        laps: list[NormalizedLap] = []

        circuit = race.get("Circuit", {})

        for result in qualifying_results:
            driver = result["Driver"]
            constructor = result.get("Constructor", {})

            # Pick the best qualifying time (Q3 > Q2 > Q1)
            best_time_str = result.get("Q3") or result.get("Q2") or result.get("Q1")
            lap_time_ms = _parse_qualifying_time(best_time_str) if best_time_str else None

            lap = NormalizedLap(
                session_id=f"ergast-qual-{race.get('season', '')}-{race.get('round', '')}",
                driver_id=driver.get("driverId"),
                driver_code=driver.get("code"),
                circuit_id=circuit.get("circuitId"),
                source="ergast",
                lap_time_ms=lap_time_ms,
                is_valid=True,
                position=int(result.get("position", 0)),
                season=int(race.get("season", 0)),
                round_number=int(race.get("round", 0)),
                team_name=constructor.get("name"),
                team_id=constructor.get("constructorId"),
            )
            laps.append(lap)

        logger.info(
            "Fetched %d qualifying results for %d round %d (%s)",
            len(laps), season, round_num, race.get("raceName", "?"),
        )
        return laps

    async def fetch_full_season(self, season: int) -> list[NormalizedLap]:
        """Fetch all race results for an entire season.

        Args:
            season: Year (e.g., 2024)

        Returns:
            List of NormalizedLap for every classified driver in every race
        """
        schedule = await self.fetch_season_schedule(season)
        all_laps: list[NormalizedLap] = []

        for race in schedule:
            round_num = int(race["round"])
            laps = await self.fetch_race_results(season, round_num)
            all_laps.extend(laps)
            # Be polite to the API
            await asyncio.sleep(0.2)

        logger.info("Season %d complete: %d total results from %d races", season, len(all_laps), len(schedule))
        return all_laps


def _parse_qualifying_time(time_str: str) -> int | None:
    """Parse a qualifying time string like '1:22.456' to milliseconds."""
    if not time_str:
        return None
    parts = time_str.split(":")
    if len(parts) == 2:
        minutes, sec_ms = parts
        seconds = float(sec_ms)
        total_seconds = int(minutes) * 60 + seconds
    else:
        total_seconds = float(parts[0])
    return int(round(total_seconds * 1000))
