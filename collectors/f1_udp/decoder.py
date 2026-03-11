"""F1 24 UDP Packet Decoder.

Decodes raw UDP bytes from the F1 24 game into structured Python dicts.
Based on the official F1 24 UDP specification:
https://answers.ea.com/t5/General-Discussion/F1-24-UDP-Specification/td-p/13745220

Packet Header (29 bytes):
    uint16  packetFormat      (2024)
    uint8   gameYear          (24)
    uint8   gameMajorVersion
    uint8   gameMinorVersion
    uint8   packetVersion
    uint8   packetId
    uint64  sessionUID
    float   sessionTime
    uint32  frameIdentifier
    uint32  overallFrameIdentifier
    uint8   playerCarIndex
    uint8   secondaryPlayerCarIndex

15 Packet Types (by packetId):
    0  = Motion
    1  = Session
    2  = Lap Data
    3  = Event
    4  = Participants
    5  = Car Setups
    6  = Car Telemetry
    7  = Car Status
    8  = Final Classification
    9  = Lobby Info
    10 = Car Damage
    11 = Session History
    12 = Tyre Sets
    13 = Motion Ex
    14 = Time Trial
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

# ============================================================
# Constants
# ============================================================
HEADER_FORMAT = "<HBBBBBQfIIBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 29 bytes

NUM_CARS = 22

# Packet ID -> name mapping
PACKET_IDS = {
    0: "motion",
    1: "session",
    2: "lap_data",
    3: "event",
    4: "participants",
    5: "car_setups",
    6: "car_telemetry",
    7: "car_status",
    8: "final_classification",
    9: "lobby_info",
    10: "car_damage",
    11: "session_history",
    12: "tyre_sets",
    13: "motion_ex",
    14: "time_trial",
}

# Track ID -> circuit identifier mapping (F1 24)
TRACK_MAP = {
    0: "melbourne",
    1: "paul_ricard",
    2: "shanghai",
    3: "sakhir",
    4: "catalunya",
    5: "monaco",
    6: "montreal",
    7: "silverstone",
    8: "hockenheim",
    9: "hungaroring",
    10: "spa",
    11: "monza_old",
    12: "singapore",
    13: "suzuka",
    14: "monza",
    15: "las_vegas",
    16: "marina_bay",
    17: "austin",
    18: "interlagos",
    19: "yas_marina",
    20: "jeddah",
    21: "miami",
    22: "imola",
    23: "portimao",
    24: "baku",
    25: "zandvoort",
    26: "lusail",
}


# ============================================================
# Header
# ============================================================
@dataclass
class F1PacketHeader:
    """Decoded F1 24 UDP packet header."""

    packet_format: int
    game_year: int
    game_major_version: int
    game_minor_version: int
    packet_version: int
    packet_id: int
    session_uid: int
    session_time: float
    frame_identifier: int
    overall_frame_identifier: int
    player_car_index: int
    secondary_player_car_index: int


def decode_header(data: bytes) -> F1PacketHeader:
    """Decode the 29-byte packet header.

    Args:
        data: Raw UDP packet bytes (at least 29 bytes)

    Returns:
        F1PacketHeader dataclass
    """
    fields = struct.unpack_from(HEADER_FORMAT, data, 0)
    return F1PacketHeader(*fields)


# ============================================================
# Packet ID 0: Motion
# ============================================================
# Per car: 6 floats + 6 int16 + 6 floats = 60 bytes
_MOTION_CAR_FORMAT = "<ffffff3h3hffffff"
_MOTION_CAR_SIZE = struct.calcsize(_MOTION_CAR_FORMAT)  # 60 bytes


def decode_motion_packet(data: bytes) -> dict[str, Any]:
    """Decode Motion packet (ID=0): 22 cars with position and g-force data."""
    offset = HEADER_SIZE
    cars = []
    for _ in range(NUM_CARS):
        fields = struct.unpack_from(_MOTION_CAR_FORMAT, data, offset)
        cars.append(
            {
                "world_position_x": fields[0],
                "world_position_y": fields[1],
                "world_position_z": fields[2],
                "world_velocity_x": fields[3],
                "world_velocity_y": fields[4],
                "world_velocity_z": fields[5],
                "world_forward_dir_x": fields[6],
                "world_forward_dir_y": fields[7],
                "world_forward_dir_z": fields[8],
                "world_right_dir_x": fields[9],
                "world_right_dir_y": fields[10],
                "world_right_dir_z": fields[11],
                "g_force_lateral": fields[12],
                "g_force_longitudinal": fields[13],
                "g_force_vertical": fields[14],
                "yaw": fields[15],
                "pitch": fields[16],
                "roll": fields[17],
            }
        )
        offset += _MOTION_CAR_SIZE
    return {"cars": cars}


# ============================================================
# Packet ID 1: Session
# ============================================================
_SESSION_FORMAT = "<BbbBHBbB"
_SESSION_SIZE = struct.calcsize(_SESSION_FORMAT)


def decode_session_packet(data: bytes) -> dict[str, Any]:
    """Decode Session packet (ID=1): weather, temps, track info."""
    offset = HEADER_SIZE
    fields = struct.unpack_from(_SESSION_FORMAT, data, offset)
    return {
        "weather": fields[0],
        "track_temperature": fields[1],
        "air_temperature": fields[2],
        "total_laps": fields[3],
        "track_length": fields[4],
        "session_type": fields[5],
        "track_id": fields[6],
        "formula": fields[7],
    }


# ============================================================
# Packet ID 2: Lap Data
# ============================================================
_LAP_CAR_FORMAT = "<IIHHHHHHfffBBBBBBBBBBBBBBBHHBfB"
_LAP_CAR_SIZE = struct.calcsize(_LAP_CAR_FORMAT)  # 57 bytes


def decode_lap_data_packet(data: bytes) -> dict[str, Any]:
    """Decode Lap Data packet (ID=2): 22 cars with lap times, sectors, position."""
    offset = HEADER_SIZE
    cars = []
    for _ in range(NUM_CARS):
        fields = struct.unpack_from(_LAP_CAR_FORMAT, data, offset)
        cars.append(
            {
                "last_lap_time_in_ms": fields[0],
                "current_lap_time_in_ms": fields[1],
                "sector1_time_in_ms": fields[2],
                "sector1_time_minutes": fields[3],
                "sector2_time_in_ms": fields[4],
                "sector2_time_minutes": fields[5],
                "delta_to_best_lap_in_ms": fields[6],
                "delta_to_race_leader_in_ms": fields[7],
                "lap_distance": fields[8],
                "total_distance": fields[9],
                "safety_car_delta": fields[10],
                "car_position": fields[11],
                "current_lap_num": fields[12],
                "pit_status": fields[13],
                "num_pit_stops": fields[14],
                "sector": fields[15],
                "current_lap_invalid": fields[16],
                "penalties": fields[17],
                "total_warnings": fields[18],
                "corner_cutting_warnings": fields[19],
                "num_unserved_drive_through_pens": fields[20],
                "num_unserved_stop_go_pens": fields[21],
                "grid_position": fields[22],
                "driver_status": fields[23],
                "result_status": fields[24],
                "pit_lane_timer_active": fields[25],
                "pit_lane_time_in_lane_in_ms": fields[26],
                "pit_stop_timer_in_ms": fields[27],
                "pit_stop_should_serve_pen": fields[28],
                "speed_trap_fastest_speed": fields[29],
                "speed_trap_fastest_lap": fields[30],
            }
        )
        offset += _LAP_CAR_SIZE
    return {"cars": cars}


# ============================================================
# Packet ID 4: Participants
# ============================================================
_PARTICIPANT_FORMAT = "<BBBBBBB48sBBHB"
_PARTICIPANT_SIZE = struct.calcsize(_PARTICIPANT_FORMAT)


def decode_participants_packet(data: bytes) -> dict[str, Any]:
    """Decode Participants packet (ID=4): driver names, teams, AI status."""
    offset = HEADER_SIZE
    num_active_cars = struct.unpack_from("<B", data, offset)[0]
    offset += 1

    participants = []
    for _ in range(NUM_CARS):
        fields = struct.unpack_from(_PARTICIPANT_FORMAT, data, offset)
        name_bytes = fields[7]
        name = name_bytes.split(b"\x00")[0].decode("utf-8", errors="replace")
        participants.append(
            {
                "ai_controlled": fields[0],
                "driver_id": fields[1],
                "network_id": fields[2],
                "team_id": fields[3],
                "my_team": fields[4],
                "race_number": fields[5],
                "nationality": fields[6],
                "name": name,
                "your_telemetry": fields[8],
                "show_online_names": fields[9],
                "tech_level": fields[10],
                "platform": fields[11],
            }
        )
        offset += _PARTICIPANT_SIZE

    return {"num_active_cars": num_active_cars, "participants": participants}


# ============================================================
# Packet ID 6: Car Telemetry
# ============================================================
_TELEMETRY_CAR_FORMAT = "<HfffBbHBBH4H4B4BH4f4B"
_TELEMETRY_CAR_SIZE = struct.calcsize(_TELEMETRY_CAR_FORMAT)


def decode_car_telemetry_packet(data: bytes) -> dict[str, Any]:
    """Decode Car Telemetry packet (ID=6): speed, throttle, brake, temps."""
    offset = HEADER_SIZE
    cars = []
    for _ in range(NUM_CARS):
        fields = struct.unpack_from(_TELEMETRY_CAR_FORMAT, data, offset)
        idx = 0
        speed = fields[idx]
        idx += 1
        throttle = fields[idx]
        idx += 1
        steer = fields[idx]
        idx += 1
        brake = fields[idx]
        idx += 1
        clutch = fields[idx]
        idx += 1
        gear = fields[idx]
        idx += 1
        engine_rpm = fields[idx]
        idx += 1
        drs = fields[idx]
        idx += 1
        rev_lights_percent = fields[idx]
        idx += 1
        _rev_lights_bit_value = fields[idx]
        idx += 1
        brakes_temp = [fields[idx + i] for i in range(4)]
        idx += 4
        tyres_surface_temp = [fields[idx + i] for i in range(4)]
        idx += 4
        tyres_inner_temp = [fields[idx + i] for i in range(4)]
        idx += 4
        engine_temp = fields[idx]
        idx += 1
        tyres_pressure = [fields[idx + i] for i in range(4)]
        idx += 4
        surface_type = [fields[idx + i] for i in range(4)]

        cars.append(
            {
                "speed": speed,
                "throttle": throttle,
                "steer": steer,
                "brake": brake,
                "clutch": clutch,
                "gear": gear,
                "engine_rpm": engine_rpm,
                "drs": drs,
                "rev_lights_percent": rev_lights_percent,
                "brakes_temperature": brakes_temp,
                "tyres_surface_temperature": tyres_surface_temp,
                "tyres_inner_temperature": tyres_inner_temp,
                "engine_temperature": engine_temp,
                "tyres_pressure": tyres_pressure,
                "surface_type": surface_type,
            }
        )
        offset += _TELEMETRY_CAR_SIZE
    return {"cars": cars}


# ============================================================
# Packet ID 7: Car Status
# ============================================================
_STATUS_CAR_FORMAT = "<BBBBBfffHHBBHBBBbffffBfffB"
_STATUS_CAR_SIZE = struct.calcsize(_STATUS_CAR_FORMAT)


def decode_car_status_packet(data: bytes) -> dict[str, Any]:
    """Decode Car Status packet (ID=7): fuel, tires, ERS."""
    offset = HEADER_SIZE
    cars = []
    for _ in range(NUM_CARS):
        fields = struct.unpack_from(_STATUS_CAR_FORMAT, data, offset)
        cars.append(
            {
                "traction_control": fields[0],
                "anti_lock_brakes": fields[1],
                "fuel_mix": fields[2],
                "front_brake_bias": fields[3],
                "pit_limiter_status": fields[4],
                "fuel_in_tank": fields[5],
                "fuel_capacity": fields[6],
                "fuel_remaining_laps": fields[7],
                "max_rpm": fields[8],
                "idle_rpm": fields[9],
                "max_gears": fields[10],
                "drs_allowed": fields[11],
                "drs_activation_distance": fields[12],
                "actual_tyre_compound": fields[13],
                "visual_tyre_compound": fields[14],
                "tyres_age_laps": fields[15],
                "vehicle_fia_flags": fields[16],
                "engine_power_ice": fields[17],
                "engine_power_mguk": fields[18],
                "ers_store_energy": fields[19],
                "ers_deploy_pct": fields[20],
                "ers_deploy_mode": fields[21],
                "ers_harvested_this_lap_mguk": fields[22],
                "ers_harvested_this_lap_mguh": fields[23],
                "ers_deployed_this_lap": fields[24],
                "network_paused": fields[25],
            }
        )
        offset += _STATUS_CAR_SIZE
    return {"cars": cars}


# ============================================================
# Dispatch
# ============================================================
_DECODERS = {
    0: decode_motion_packet,
    1: decode_session_packet,
    2: decode_lap_data_packet,
    4: decode_participants_packet,
    6: decode_car_telemetry_packet,
    7: decode_car_status_packet,
}


def decode_packet(data: bytes) -> tuple[F1PacketHeader, dict[str, Any] | None]:
    """Decode any F1 24 UDP packet.

    First decodes the header, then dispatches to the appropriate decoder
    based on packetId. Returns (header, decoded_data) where decoded_data
    is None for unrecognized packet types.

    Args:
        data: Raw UDP packet bytes

    Returns:
        Tuple of (header, decoded_dict_or_None)
    """
    header = decode_header(data)
    decoder = _DECODERS.get(header.packet_id)
    if decoder is None:
        return header, None
    return header, decoder(data)
