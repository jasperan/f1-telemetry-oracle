"""OpenF1 Collector — fetches live and historical F1 data from the OpenF1 API.

Supports:
- Batch mode: backfill sessions from 2023-2025
- Live polling mode (see Task 10)

OpenF1 API: https://openf1.org — no API key required, rate-limited to ~4 req/s.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from collectors.normalizer import NormalizedFrame, NormalizedLap, normalize_openf1_lap

logger = logging.getLogger(__name__)


class OpenF1Collector:
    """Async collector for the OpenF1 API."""

    def __init__(
        self,
        base_url: str = "https://api.openf1.org/v1",
        max_retries: int = 3,
        retry_delay: float = 0.5,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._timeout = timeout

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        """Make a GET request with retry on 429 / 5xx.

        Args:
            path: URL path relative to base_url (e.g., "/sessions")
            params: Query parameters

        Returns:
            Parsed JSON response body (list or dict)
        """
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(self._max_retries):
                try:
                    response = await client.get(url, params=params)

                    if response.status_code == 429:
                        delay = self._retry_delay * (2**attempt)
                        logger.warning(
                            "Rate limited (429) on %s, retry %d/%d in %.1fs",
                            url,
                            attempt + 1,
                            self._max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    if response.status_code >= 500:
                        delay = self._retry_delay * (2**attempt)
                        logger.warning(
                            "Server error (%d) on %s, retry %d/%d in %.1fs",
                            response.status_code,
                            url,
                            attempt + 1,
                            self._max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    response.raise_for_status()
                    return response.json()

                except httpx.TimeoutException as exc:
                    last_exc = exc
                    delay = self._retry_delay * (2**attempt)
                    logger.warning("Timeout on %s, retry %d/%d in %.1fs", url, attempt + 1, self._max_retries, delay)
                    await asyncio.sleep(delay)

        if last_exc:
            raise last_exc
        raise httpx.HTTPStatusError(
            f"Failed after {self._max_retries} retries",
            request=httpx.Request("GET", url),
            response=httpx.Response(500),
        )

    async def _fetch_paginated(
        self,
        path: str,
        params: dict[str, str] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch all pages of a paginated OpenF1 endpoint.

        OpenF1 uses offset/limit pagination. An empty response signals the end.

        Args:
            path: API path (e.g., "/laps")
            params: Base query parameters (session_key, etc.)
            page_size: Number of records per page

        Returns:
            Combined list of all records across pages
        """
        all_records: list[dict[str, Any]] = []
        offset = 0
        base_params = dict(params or {})

        while True:
            page_params = {**base_params, "offset": str(offset), "limit": str(page_size)}
            page = await self._get_json(path, params=page_params)

            if not page:  # empty list = no more data
                break

            all_records.extend(page)
            offset += len(page)

            if len(page) < page_size:
                break  # partial page = last page

        return all_records

    async def fetch_session(self, session_key: int) -> dict[str, Any]:
        """Fetch metadata for a single session.

        Args:
            session_key: OpenF1 session identifier

        Returns:
            Session metadata dict

        Raises:
            ValueError: If session not found
        """
        data = await self._get_json("/sessions", params={"session_key": str(session_key)})
        if not data:
            raise ValueError(f"Session {session_key} not found")
        return data[0]

    async def fetch_laps(
        self,
        session_key: int,
        circuit_short_name: str = "",
    ) -> list[NormalizedLap]:
        """Fetch all laps for a session and normalize them.

        Enriches laps with driver info and stint/tire data from companion endpoints.

        Args:
            session_key: OpenF1 session identifier
            circuit_short_name: Circuit name for normalization context

        Returns:
            Deduplicated list of NormalizedLap objects
        """
        # Fetch raw laps
        raw_laps = await self._get_json("/laps", params={"session_key": str(session_key)})
        if not raw_laps:
            return []

        # Fetch driver info and stints for enrichment
        drivers_data = await self._get_json("/drivers", params={"session_key": str(session_key)})
        stints_data = await self._get_json("/stints", params={"session_key": str(session_key)})

        # Build lookup maps
        driver_map: dict[int, dict[str, Any]] = {}
        for d in drivers_data or []:
            driver_map[d["driver_number"]] = d

        # Build stint lookup: driver_number -> list of stint dicts sorted by lap_start
        stint_map: dict[int, list[dict[str, Any]]] = {}
        for s in stints_data or []:
            stint_map.setdefault(s["driver_number"], []).append(s)
        for stints in stint_map.values():
            stints.sort(key=lambda x: x.get("lap_start", 0))

        # Deduplicate by (driver_number, lap_number, date_start)
        seen: set[tuple[int, int, str]] = set()
        unique_laps: list[dict[str, Any]] = []
        for lap in raw_laps:
            key = (
                lap.get("driver_number", 0),
                lap.get("lap_number", 0),
                lap.get("date_start", ""),
            )
            if key not in seen:
                seen.add(key)
                unique_laps.append(lap)

        # Enrich and normalize
        normalized: list[NormalizedLap] = []
        for lap in unique_laps:
            dn = lap.get("driver_number", 0)

            # Merge driver info
            driver = driver_map.get(dn, {})
            lap["driver_code"] = driver.get("name_acronym")
            lap["driver_first_name"] = driver.get("first_name")
            lap["driver_last_name"] = driver.get("last_name")
            lap["team_name"] = driver.get("team_name")

            # Find matching stint for tire info
            for stint in stint_map.get(dn, []):
                lap_num = lap.get("lap_number", 0)
                if stint.get("lap_start", 0) <= lap_num <= stint.get("lap_end", 9999):
                    lap["compound"] = stint.get("compound")
                    lap["tyre_age_at_start"] = stint.get("tyre_age_at_start", 0) + (
                        lap_num - stint.get("lap_start", 0)
                    )
                    break

            lap["circuit_short_name"] = circuit_short_name
            normalized.append(normalize_openf1_lap(lap))

        logger.info(
            "Fetched %d laps for session %d (%d raw, %d after dedup)",
            len(normalized),
            session_key,
            len(raw_laps),
            len(unique_laps),
        )
        return normalized

    async def fetch_car_data(
        self,
        session_key: int,
        driver_number: int,
    ) -> list[NormalizedFrame]:
        """Fetch high-frequency car telemetry for a specific driver.

        Args:
            session_key: OpenF1 session identifier
            driver_number: Driver's car number

        Returns:
            List of NormalizedFrame objects
        """
        data = await self._get_json(
            "/car_data",
            params={"session_key": str(session_key), "driver_number": str(driver_number)},
        )
        if not data:
            return []

        frames: list[NormalizedFrame] = []
        for sample in data:
            # Parse ISO timestamp to epoch ms
            date_str = sample.get("date", "")
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                ts_ms = int(dt.timestamp() * 1000)
            except (ValueError, AttributeError):
                ts_ms = 0

            frame = NormalizedFrame(
                timestamp_ms=ts_ms,
                speed_kph=float(sample.get("speed", 0)),
                throttle_pct=float(sample.get("throttle", 0)),
                brake_pct=float(sample.get("brake", 0)),
                gear=int(sample.get("n_gear", 0)),
                rpm=int(sample.get("rpm", 0)),
                drs=int(sample.get("drs", 0)),
            )
            frames.append(frame)

        logger.info("Fetched %d car_data frames for driver %d session %d", len(frames), driver_number, session_key)
        return frames

    async def fetch_session_backfill(self, session_key: int) -> dict[str, Any]:
        """Full batch backfill: fetch session + laps + car_data for all drivers.

        Args:
            session_key: OpenF1 session identifier

        Returns:
            Dict with keys: session, laps, frames_by_driver
        """
        session = await self.fetch_session(session_key)
        circuit = session.get("circuit_short_name", "")

        laps = await self.fetch_laps(session_key=session_key, circuit_short_name=circuit)

        # Get unique driver numbers from laps
        driver_numbers = list({lap.driver_id.split("-")[-1] for lap in laps if lap.driver_id})

        frames_by_driver: dict[str, list[NormalizedFrame]] = {}
        for dn_str in driver_numbers:
            try:
                dn = int(dn_str)
                frames = await self.fetch_car_data(session_key=session_key, driver_number=dn)
                frames_by_driver[dn_str] = frames
                # Rate limit: pause between driver fetches
                await asyncio.sleep(0.25)
            except (ValueError, httpx.HTTPStatusError) as exc:
                logger.warning("Failed to fetch car_data for driver %s: %s", dn_str, exc)

        logger.info(
            "Backfill complete for session %d: %d laps, %d drivers with frames",
            session_key,
            len(laps),
            len(frames_by_driver),
        )
        return {"session": session, "laps": laps, "frames_by_driver": frames_by_driver}

    # --- Live polling methods (Task 10) ---

    def _dedup_laps(
        self,
        raw_laps: list[dict[str, Any]],
        seen: set[tuple[int, int, str]],
    ) -> list[dict[str, Any]]:
        """Filter out laps already seen in previous polls.

        Updates the `seen` set in-place with new entries.

        Args:
            raw_laps: Raw lap dicts from OpenF1 API
            seen: Set of (driver_number, lap_number, date_start) tuples already processed

        Returns:
            Only the laps not in `seen`
        """
        new_laps: list[dict[str, Any]] = []
        for lap in raw_laps:
            key = (
                lap.get("driver_number", 0),
                lap.get("lap_number", 0),
                lap.get("date_start", ""),
            )
            if key not in seen:
                seen.add(key)
                new_laps.append(lap)
        return new_laps

    async def live_poll(
        self,
        session_key: int,
        circuit_short_name: str,
        callback: Any,
        poll_interval: float = 2.0,
        max_polls: int = 0,
    ) -> None:
        """Poll OpenF1 for new laps at a fixed interval.

        Tracks seen laps by (driver_number, lap_number, date_start) to avoid
        re-processing duplicates. Calls `callback(new_laps)` with only the
        newly-seen NormalizedLap objects each cycle.

        Args:
            session_key: OpenF1 session identifier
            circuit_short_name: Circuit name for normalization
            callback: Async callable receiving list[NormalizedLap]
            poll_interval: Seconds between polls (default 2.0)
            max_polls: Stop after this many polls (0 = infinite, for production use)
        """
        # Pre-fetch driver and stint data (changes infrequently)
        drivers_data = await self._get_json("/drivers", params={"session_key": str(session_key)})
        stints_data = await self._get_json("/stints", params={"session_key": str(session_key)})

        driver_map: dict[int, dict[str, Any]] = {}
        for d in drivers_data or []:
            driver_map[d["driver_number"]] = d

        stint_map: dict[int, list[dict[str, Any]]] = {}
        for s in stints_data or []:
            stint_map.setdefault(s["driver_number"], []).append(s)
        for stints in stint_map.values():
            stints.sort(key=lambda x: x.get("lap_start", 0))

        seen: set[tuple[int, int, str]] = set()
        poll_count = 0

        while True:
            poll_count += 1

            # Fetch raw laps
            raw_laps = await self._get_json("/laps", params={"session_key": str(session_key)})
            if raw_laps is None:
                raw_laps = []

            # Dedup against previously seen
            new_raw = self._dedup_laps(raw_laps, seen)

            if new_raw:
                # Enrich and normalize
                normalized: list[NormalizedLap] = []
                for lap in new_raw:
                    dn = lap.get("driver_number", 0)
                    driver = driver_map.get(dn, {})
                    lap["driver_code"] = driver.get("name_acronym")
                    lap["driver_first_name"] = driver.get("first_name")
                    lap["driver_last_name"] = driver.get("last_name")
                    lap["team_name"] = driver.get("team_name")

                    for stint in stint_map.get(dn, []):
                        lap_num = lap.get("lap_number", 0)
                        if stint.get("lap_start", 0) <= lap_num <= stint.get("lap_end", 9999):
                            lap["compound"] = stint.get("compound")
                            lap["tyre_age_at_start"] = stint.get("tyre_age_at_start", 0) + (
                                lap_num - stint.get("lap_start", 0)
                            )
                            break

                    lap["circuit_short_name"] = circuit_short_name
                    normalized.append(normalize_openf1_lap(lap))

                logger.info("Live poll %d: %d new laps", poll_count, len(normalized))
                await callback(normalized)
            else:
                logger.debug("Live poll %d: no new data", poll_count)

            if max_polls > 0 and poll_count >= max_polls:
                logger.info("Reached max_polls=%d, stopping", max_polls)
                break

            await asyncio.sleep(poll_interval)
