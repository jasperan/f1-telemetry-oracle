"""Shared SQL column lists for the laps and telemetry_frames tables.

Hoisted into one place so the laps and compare routers (and any future
consumers) agree on column order, which the row-mapping helpers depend on.
"""

from __future__ import annotations

LAP_COLUMNS = (
    "lap_id, session_id, driver_id, lap_number, "
    "sector1_ms, sector2_ms, sector3_ms, lap_time_ms, "
    "tire_compound, tire_age_laps, fuel_load_kg, ers_deploy_pct, "
    "is_valid, position, created_at"
)

FRAME_COLUMNS = (
    "frame_id, lap_id, timestamp_ms, distance_m, speed_kph, "
    "throttle_pct, brake_pct, steering, gear, rpm, drs, "
    "pos_x, pos_y, pos_z, g_lat, g_lon, "
    "tire_temp_fl, tire_temp_fr, tire_temp_rl, tire_temp_rr, "
    "brake_temp_fl, brake_temp_fr, brake_temp_rl, brake_temp_rr"
)
