"""Test that all three data sources normalize to identical NormalizedLap structure."""


from collectors.normalizer import (
    NormalizedLap,
    normalize_ergast_result,
    normalize_f1_udp_lap,
    normalize_openf1_lap,
)

# === Mock F1 24 UDP packet (decoded from binary) ===
MOCK_F1_UDP_LAP = {
    "header": {
        "session_uid": 12345678,
        "frame_identifier": 9001,
    },
    "lap_data": {
        "current_lap_num": 5,
        "sector1_time_in_ms": 28512,
        "sector2_time_in_ms": 33180,
        "sector3_time_in_ms": 24308,
        "last_lap_time_in_ms": 86000,
        "current_lap_invalid": 0,
        "pit_status": 0,
        "driver_status": 0,
        "result_status": 2,  # active
        "grid_position": 3,
    },
    "car_status": {
        "tyre_compound_visual": 16,    # SOFT
        "tyres_age_laps": 3,
        "fuel_in_tank": 42.5,
        "ers_deploy_mode": 3,
    },
    "participants": {
        "driver_id": 0,  # player
        "name": "Player",
        "team_id": 0,
    },
    "session_info": {
        "circuit_id": "monza",
        "session_type": "race",
    },
}

# === Mock OpenF1 API response ===
MOCK_OPENF1_LAP = {
    "driver_number": 1,
    "meeting_key": 1234,
    "session_key": 9876,
    "lap_number": 12,
    "lap_duration": 81.456,
    "duration_sector_1": 27.123,
    "duration_sector_2": 31.456,
    "duration_sector_3": 22.877,
    "is_pit_out_lap": False,
    "segments_sector_1": [2048, 2049, 2049],
    "segments_sector_2": [2048, 2048],
    "segments_sector_3": [2049, 2049],
    "st_speed": 342.5,
    # Context data (joined from other endpoints)
    "driver_code": "VER",
    "driver_first_name": "Max",
    "driver_last_name": "Verstappen",
    "team_name": "Red Bull Racing",
    "compound": "MEDIUM",
    "tyre_age_at_start": 5,
    "circuit_short_name": "Monza",
}

# === Mock Ergast API response ===
MOCK_ERGAST_RESULT = {
    "season": "2024",
    "round": "16",
    "raceName": "Italian Grand Prix",
    "Circuit": {
        "circuitId": "monza",
        "circuitName": "Autodromo Nazionale Monza",
        "Location": {
            "lat": "45.6156",
            "long": "9.2811",
            "locality": "Monza",
            "country": "Italy",
        },
    },
    "Results": [
        {
            "number": "1",
            "position": "1",
            "Driver": {
                "driverId": "max_verstappen",
                "code": "VER",
                "givenName": "Max",
                "familyName": "Verstappen",
                "nationality": "Dutch",
            },
            "Constructor": {
                "constructorId": "red_bull",
                "name": "Red Bull",
            },
            "grid": "1",
            "laps": "53",
            "status": "Finished",
            "Time": {"millis": "4576234", "time": "1:16:16.234"},
            "FastestLap": {
                "rank": "1",
                "lap": "42",
                "Time": {"time": "1:24.292"},
                "AverageSpeed": {"units": "kph", "speed": "247.585"},
            },
        }
    ],
}


class TestNormalizeLap:
    def test_f1_udp_produces_normalized_lap(self):
        lap = normalize_f1_udp_lap(MOCK_F1_UDP_LAP)
        assert isinstance(lap, NormalizedLap)
        assert lap.source == "sim"
        assert lap.lap_number == 5
        assert lap.sector1_ms == 28512
        assert lap.sector2_ms == 33180
        assert lap.sector3_ms == 24308
        assert lap.lap_time_ms == 86000
        assert lap.tire_compound == "SOFT"
        assert lap.tire_age_laps == 3
        assert lap.fuel_load_kg == 42.5
        assert lap.is_valid is True
        assert lap.driver_id is not None

    def test_openf1_produces_normalized_lap(self):
        lap = normalize_openf1_lap(MOCK_OPENF1_LAP)
        assert isinstance(lap, NormalizedLap)
        assert lap.source == "openf1"
        assert lap.lap_number == 12
        # OpenF1 gives seconds as float — we store as int ms
        assert lap.sector1_ms == 27123
        assert lap.sector2_ms == 31456
        assert lap.sector3_ms == 22877
        assert lap.lap_time_ms == 81456
        assert lap.tire_compound == "MEDIUM"
        assert lap.tire_age_laps == 5
        assert lap.driver_code == "VER"
        assert lap.is_valid is True

    def test_ergast_produces_normalized_lap(self):
        lap = normalize_ergast_result(MOCK_ERGAST_RESULT, driver_index=0)
        assert isinstance(lap, NormalizedLap)
        assert lap.source == "ergast"
        assert lap.driver_id == "max_verstappen"
        assert lap.driver_code == "VER"
        assert lap.circuit_id == "monza"
        assert lap.position == 1
        assert lap.lap_time_ms == 84292  # 1:24.292 = 84292ms
        assert lap.season == 2024
        assert lap.round_number == 16

    def test_all_sources_share_same_schema(self):
        """All three produce NormalizedLap with the same field set."""
        udp = normalize_f1_udp_lap(MOCK_F1_UDP_LAP)
        openf1 = normalize_openf1_lap(MOCK_OPENF1_LAP)
        ergast = normalize_ergast_result(MOCK_ERGAST_RESULT, driver_index=0)

        # All must have these core fields set
        for lap in [udp, openf1, ergast]:
            assert lap.source is not None
            assert lap.lap_number is not None or lap.source == "ergast"
            assert lap.driver_id is not None or lap.driver_code is not None
            assert lap.lap_time_ms is not None or lap.lap_time_ms == 0


class TestNormalizedLapFields:
    def test_udp_tire_compound_mapping(self):
        """UDP visual compound IDs map to human-readable names."""
        lap = normalize_f1_udp_lap(MOCK_F1_UDP_LAP)
        assert lap.tire_compound in ("SOFT", "MEDIUM", "HARD", "INTER", "WET")

    def test_openf1_sector_float_to_int_ms(self):
        """OpenF1 sector durations (float seconds) convert to integer milliseconds."""
        lap = normalize_openf1_lap(MOCK_OPENF1_LAP)
        assert isinstance(lap.sector1_ms, int)
        assert isinstance(lap.sector2_ms, int)
        assert isinstance(lap.sector3_ms, int)
        assert isinstance(lap.lap_time_ms, int)

    def test_ergast_time_string_parsing(self):
        """Ergast fastest lap time string '1:24.292' parses to 84292 ms."""
        lap = normalize_ergast_result(MOCK_ERGAST_RESULT, driver_index=0)
        assert lap.lap_time_ms == 84292
