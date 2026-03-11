-- Seed data for integration tests.
-- Minimal but complete: 1 circuit, 2 drivers, 1 team, 1 session, 2 laps with telemetry.

INSERT INTO circuits (circuit_id, circuit_name, country, locality, track_length_m, lat, lng)
VALUES ('monza', 'Autodromo Nazionale Monza', 'Italy', 'Monza', 5793, 45.6156, 9.2811);

INSERT INTO teams (team_id, team_name, color_hex, engine)
VALUES ('red_bull', 'Red Bull Racing', '#3671C6', 'Honda RBPT');

INSERT INTO drivers (driver_id, code, first_name, last_name, driver_number, nationality, is_sim_player)
VALUES ('verstappen', 'VER', 'Max', 'Verstappen', 1, 'NLD', 0);

INSERT INTO drivers (driver_id, code, first_name, last_name, driver_number, nationality, is_sim_player)
VALUES ('sim_player', 'SIM', 'Sim', 'Player', 99, 'SIM', 1);

INSERT INTO sessions (session_id, circuit_id, session_type, source, started_at)
VALUES ('monza_2024_r', 'monza', 'race', 'openf1', TIMESTAMP '2024-09-01 14:00:00');

INSERT INTO laps (lap_id, session_id, driver_id, lap_number, sector1_ms, sector2_ms, sector3_ms, lap_time_ms, tire_compound, tire_age_laps, fuel_load_kg, ers_deploy_pct)
VALUES ('lap_ver_1', 'monza_2024_r', 'verstappen', 1, 28500, 33200, 24100, 85800, 'SOFT', 1, 95.0, 0.75);

INSERT INTO laps (lap_id, session_id, driver_id, lap_number, sector1_ms, sector2_ms, sector3_ms, lap_time_ms, tire_compound, tire_age_laps, fuel_load_kg, ers_deploy_pct)
VALUES ('lap_sim_1', 'monza_2024_r', 'sim_player', 1, 29100, 34000, 24800, 87900, 'SOFT', 1, 95.0, 0.70);

INSERT INTO telemetry_frames (frame_id, lap_id, timestamp_ms, distance_m, speed_kph, throttle_pct, brake_pct, steering, gear, rpm, drs)
VALUES ('frame_ver_1_0', 'lap_ver_1', 0, 0, 0.0, 100.0, 0.0, 0.0, 1, 8500, 0);

INSERT INTO telemetry_frames (frame_id, lap_id, timestamp_ms, distance_m, speed_kph, throttle_pct, brake_pct, steering, gear, rpm, drs)
VALUES ('frame_ver_1_1000', 'lap_ver_1', 1000, 82.5, 297.3, 100.0, 0.0, -1.2, 8, 11200, 1);

INSERT INTO telemetry_frames (frame_id, lap_id, timestamp_ms, distance_m, speed_kph, throttle_pct, brake_pct, steering, gear, rpm, drs)
VALUES ('frame_sim_1_0', 'lap_sim_1', 0, 0, 0.0, 100.0, 0.0, 0.0, 1, 8200, 0);

INSERT INTO telemetry_frames (frame_id, lap_id, timestamp_ms, distance_m, speed_kph, throttle_pct, brake_pct, steering, gear, rpm, drs)
VALUES ('frame_sim_1_1000', 'lap_sim_1', 1000, 78.1, 281.4, 95.0, 0.0, -2.1, 7, 10800, 1);
