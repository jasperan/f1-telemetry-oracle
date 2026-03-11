"""Unified Normalizer — maps F1 UDP, OpenF1, and Ergast data to common dataclasses.

All three data sources produce NormalizedLap (and optionally NormalizedFrame for
per-sample telemetry). This is the single source of truth for what gets written to Oracle.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedFrame:
    """A single telemetry sample at one point in time/distance."""

    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    lap_id: str | None = None
    timestamp_ms: int = 0
    distance_m: float = 0.0
    speed_kph: float = 0.0
    throttle_pct: float = 0.0
    brake_pct: float = 0.0
    steering: float = 0.0
    gear: int = 0
    rpm: int = 0
    drs: int = 0
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    g_lat: float = 0.0
    g_lon: float = 0.0
    tire_temp_fl: float = 0.0
    tire_temp_fr: float = 0.0
    tire_temp_rl: float = 0.0
    tire_temp_rr: float = 0.0
    brake_temp_fl: float = 0.0
    brake_temp_fr: float = 0.0
    brake_temp_rl: float = 0.0
    brake_temp_rr: float = 0.0


@dataclass
class NormalizedLap:
    """A single lap from any source — the universal exchange format."""

    lap_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    driver_id: str | None = None
    driver_code: str | None = None
    circuit_id: str | None = None
    source: str = ""  # "sim", "openf1", "ergast"
    lap_number: int | None = None
    sector1_ms: int | None = None
    sector2_ms: int | None = None
    sector3_ms: int | None = None
    lap_time_ms: int | None = None
    tire_compound: str | None = None
    tire_age_laps: int | None = None
    fuel_load_kg: float | None = None
    ers_deploy_pct: float | None = None
    is_valid: bool = True
    position: int | None = None
    season: int | None = None
    round_number: int | None = None
    team_name: str | None = None
    team_id: str | None = None
    frames: list[NormalizedFrame] = field(default_factory=list)


# ============================================================
# Tire compound mapping for F1 24 game UDP
# ============================================================
_UDP_TIRE_COMPOUND_MAP = {
    16: "SOFT",
    17: "MEDIUM",
    18: "HARD",
    7: "INTER",
    8: "WET",
    # F1 24 classic compounds
    9: "DRY",
    10: "WET",
    11: "SUPER_SOFT",
    12: "SOFT",
    13: "MEDIUM",
    14: "HARD",
    15: "WET",
}


def _seconds_to_ms(seconds: float | None) -> int | None:
    """Convert a float seconds value to integer milliseconds."""
    if seconds is None:
        return None
    return int(round(seconds * 1000))


def _parse_lap_time_string(time_str: str) -> int:
    """Parse an Ergast-style lap time string to milliseconds.

    Formats:
        "1:24.292"  -> 84292 ms   (minutes:seconds.millis)
        "24.292"    -> 24292 ms   (seconds.millis)
        "1:16:16.234" -> 4576234 ms (hours:minutes:seconds.millis)
    """
    parts = time_str.split(":")
    if len(parts) == 3:
        hours, minutes, sec_ms = parts
        seconds = float(sec_ms)
        total_seconds = int(hours) * 3600 + int(minutes) * 60 + seconds
    elif len(parts) == 2:
        minutes, sec_ms = parts
        seconds = float(sec_ms)
        total_seconds = int(minutes) * 60 + seconds
    else:
        total_seconds = float(parts[0])
    return int(round(total_seconds * 1000))


# ============================================================
# F1 24 UDP normalization
# ============================================================
def normalize_f1_udp_lap(packet: dict[str, Any]) -> NormalizedLap:
    """Normalize a decoded F1 24 UDP lap packet to NormalizedLap.

    Args:
        packet: Dictionary with keys: header, lap_data, car_status, participants, session_info

    Returns:
        NormalizedLap with source="sim"
    """
    lap_data = packet["lap_data"]
    car_status = packet["car_status"]
    participants = packet["participants"]
    session_info = packet["session_info"]

    # Map UDP visual compound ID to name
    compound_id = car_status.get("tyre_compound_visual", 0)
    tire_compound = _UDP_TIRE_COMPOUND_MAP.get(compound_id, f"UNKNOWN_{compound_id}")

    # Driver ID: for the player, use "player"; for AI drivers, use the driver index
    driver_id_raw = participants.get("driver_id", 0)
    is_player = driver_id_raw == 0
    driver_id = "sim-player" if is_player else f"sim-ai-{driver_id_raw}"

    return NormalizedLap(
        session_id=str(packet["header"].get("session_uid", "")),
        driver_id=driver_id,
        driver_code=participants.get("name", "PLR")[:3].upper() if is_player else None,
        circuit_id=session_info.get("circuit_id"),
        source="sim",
        lap_number=lap_data.get("current_lap_num"),
        sector1_ms=lap_data.get("sector1_time_in_ms"),
        sector2_ms=lap_data.get("sector2_time_in_ms"),
        sector3_ms=lap_data.get("sector3_time_in_ms"),
        lap_time_ms=lap_data.get("last_lap_time_in_ms"),
        tire_compound=tire_compound,
        tire_age_laps=car_status.get("tyres_age_laps"),
        fuel_load_kg=car_status.get("fuel_in_tank"),
        ers_deploy_pct=car_status.get("ers_deploy_mode"),
        is_valid=lap_data.get("current_lap_invalid", 0) == 0,
        position=lap_data.get("grid_position"),
    )


# ============================================================
# OpenF1 API normalization
# ============================================================
def normalize_openf1_lap(data: dict[str, Any]) -> NormalizedLap:
    """Normalize an OpenF1 API lap response to NormalizedLap.

    Args:
        data: Dictionary from OpenF1 /v1/laps endpoint (with driver/stint context merged)

    Returns:
        NormalizedLap with source="openf1"
    """
    return NormalizedLap(
        session_id=str(data.get("session_key", "")),
        driver_id=f"openf1-{data.get('driver_number', 0)}",
        driver_code=data.get("driver_code"),
        circuit_id=data.get("circuit_short_name", "").lower().replace(" ", "-") if data.get("circuit_short_name") else None,
        source="openf1",
        lap_number=data.get("lap_number"),
        sector1_ms=_seconds_to_ms(data.get("duration_sector_1")),
        sector2_ms=_seconds_to_ms(data.get("duration_sector_2")),
        sector3_ms=_seconds_to_ms(data.get("duration_sector_3")),
        lap_time_ms=_seconds_to_ms(data.get("lap_duration")),
        tire_compound=data.get("compound"),
        tire_age_laps=data.get("tyre_age_at_start"),
        is_valid=not data.get("is_pit_out_lap", False),
        team_name=data.get("team_name"),
    )


# ============================================================
# Ergast API normalization
# ============================================================
def normalize_ergast_result(race_data: dict[str, Any], driver_index: int = 0) -> NormalizedLap:
    """Normalize an Ergast API race result to NormalizedLap.

    Ergast provides aggregate race results, not per-lap telemetry.
    We extract the fastest lap as the representative lap.

    Args:
        race_data: Dictionary from Ergast /api/f1/{season}/{round}/results.json
        driver_index: Index into the Results array

    Returns:
        NormalizedLap with source="ergast"
    """
    result = race_data["Results"][driver_index]
    driver = result["Driver"]
    constructor = result.get("Constructor", {})
    circuit = race_data.get("Circuit", {})

    # Parse fastest lap time if available
    fastest_lap = result.get("FastestLap", {})
    fastest_time_str = fastest_lap.get("Time", {}).get("time")
    lap_time_ms = _parse_lap_time_string(fastest_time_str) if fastest_time_str else None

    return NormalizedLap(
        session_id=f"ergast-{race_data.get('season', '')}-{race_data.get('round', '')}",
        driver_id=driver.get("driverId"),
        driver_code=driver.get("code"),
        circuit_id=circuit.get("circuitId"),
        source="ergast",
        lap_number=int(fastest_lap.get("lap", 0)) if fastest_lap.get("lap") else None,
        lap_time_ms=lap_time_ms,
        is_valid=True,
        position=int(result.get("position", 0)),
        season=int(race_data.get("season", 0)),
        round_number=int(race_data.get("round", 0)),
        team_name=constructor.get("name"),
        team_id=constructor.get("constructorId"),
    )
