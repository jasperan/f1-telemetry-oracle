"""Test F1 24 UDP packet decoder against binary fixtures."""

import struct

from collectors.f1_udp.decoder import (
    F1PacketHeader,
    decode_car_status_packet,
    decode_car_telemetry_packet,
    decode_header,
    decode_lap_data_packet,
    decode_motion_packet,
    decode_packet,
    decode_participants_packet,
    decode_session_packet,
)
from tests.fixtures.f1_24_packets import (
    HEADER_FORMAT,
    HEADER_SIZE,
    make_car_status_packet,
    make_car_telemetry_packet,
    make_lap_data_packet,
    make_motion_packet,
    make_participants_packet,
    make_session_packet,
)


class TestHeader:
    def test_decode_header(self):
        raw = make_motion_packet()
        header = decode_header(raw)
        assert isinstance(header, F1PacketHeader)
        assert header.packet_format == 2024
        assert header.game_year == 24
        assert header.packet_id == 0  # motion
        assert header.session_uid == 123456789
        assert header.player_car_index == 0

    def test_header_size(self):
        assert HEADER_SIZE == 29


class TestMotionPacket:
    def test_decode_motion(self):
        raw = make_motion_packet()
        result = decode_motion_packet(raw)
        assert len(result["cars"]) == 22

        player = result["cars"][0]
        assert abs(player["world_position_x"] - 100.0) < 0.01
        assert abs(player["world_position_z"] - 200.0) < 0.01
        assert abs(player["g_force_lateral"] - 0.5) < 0.01
        assert abs(player["g_force_longitudinal"] - 1.2) < 0.01


class TestSessionPacket:
    def test_decode_session(self):
        raw = make_session_packet()
        result = decode_session_packet(raw)
        assert result["weather"] == 0
        assert result["track_temperature"] == 38
        assert result["air_temperature"] == 25
        assert result["total_laps"] == 53
        assert result["track_length"] == 5793
        assert result["session_type"] == 10  # Race
        assert result["track_id"] == 14  # Monza


class TestLapDataPacket:
    def test_decode_lap_data(self):
        raw = make_lap_data_packet()
        result = decode_lap_data_packet(raw)
        assert len(result["cars"]) == 22

        player = result["cars"][0]
        assert player["last_lap_time_in_ms"] == 86000
        assert player["sector1_time_in_ms"] == 28512
        assert player["sector2_time_in_ms"] == 33180
        assert player["current_lap_num"] == 5
        assert player["car_position"] == 1
        assert player["current_lap_invalid"] == 0
        assert player["grid_position"] == 1

    def test_ai_car_different_values(self):
        raw = make_lap_data_packet()
        result = decode_lap_data_packet(raw)
        ai_car = result["cars"][1]
        assert ai_car["last_lap_time_in_ms"] == 87000
        assert ai_car["car_position"] == 2


class TestCarTelemetryPacket:
    def test_decode_car_telemetry(self):
        raw = make_car_telemetry_packet()
        result = decode_car_telemetry_packet(raw)
        assert len(result["cars"]) == 22

        player = result["cars"][0]
        assert player["speed"] == 320
        assert abs(player["throttle"] - 1.0) < 0.01
        assert player["gear"] == 8
        assert player["engine_rpm"] == 12500
        assert player["drs"] == 1
        assert player["brakes_temperature"] == [800, 810, 780, 790]
        assert player["tyres_surface_temperature"] == [105, 107, 100, 102]


class TestCarStatusPacket:
    def test_decode_car_status(self):
        raw = make_car_status_packet()
        result = decode_car_status_packet(raw)
        assert len(result["cars"]) == 22

        player = result["cars"][0]
        assert abs(player["fuel_in_tank"] - 42.5) < 0.01
        assert player["visual_tyre_compound"] == 16  # SOFT
        assert player["tyres_age_laps"] == 3
        assert player["ers_deploy_mode"] == 3


class TestParticipantsPacket:
    def test_decode_participants(self):
        raw = make_participants_packet()
        result = decode_participants_packet(raw)
        assert result["num_active_cars"] == 22
        assert len(result["participants"]) == 22

        player = result["participants"][0]
        assert player["ai_controlled"] == 0
        assert player["driver_id"] == 0
        assert player["name"] == "Player"

        ver = result["participants"][1]
        assert ver["ai_controlled"] == 1
        assert ver["name"] == "Verstappen"


class TestDispatch:
    def test_decode_packet_dispatches_by_id(self):
        for pid, raw_fn in [
            (0, make_motion_packet),
            (1, make_session_packet),
            (2, make_lap_data_packet),
            (6, make_car_telemetry_packet),
            (7, make_car_status_packet),
            (4, make_participants_packet),
        ]:
            raw = raw_fn()
            header, data = decode_packet(raw)
            assert header.packet_id == pid
            assert data is not None

    def test_unknown_packet_id_returns_none_data(self):
        """Unknown packet IDs should return header but None data."""
        raw = struct.pack(
            HEADER_FORMAT,
            2024,
            24,
            1,
            12,
            1,
            99,  # unknown packet ID
            123456789,
            42.5,
            9001,
            9001,
            0,
            255,
        )
        raw += b"\x00" * 100  # padding
        header, data = decode_packet(raw)
        assert header.packet_id == 99
        assert data is None
