"""F1 24 Async UDP Listener.

Receives UDP packets from the F1 24 game, decodes them, and produces
NormalizedLap and NormalizedFrame objects via callbacks.

The listener maintains state across packet types to assemble complete
lap data (which requires combining lap_data, car_status, participants,
and session packets).

Usage:
    listener = F1UDPListener(host="0.0.0.0", port=20777, on_lap=my_callback)
    transport, port = await listener.start()
    # ... runs until listener.stop()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from collectors.f1_udp.decoder import (
    TRACK_MAP,
    F1PacketHeader,
    decode_packet,
)
from collectors.normalizer import (
    NormalizedFrame,
    NormalizedLap,
    normalize_f1_udp_lap,
)

logger = logging.getLogger(__name__)

# Type aliases for callbacks
OnPacketCallback = Callable[[F1PacketHeader, dict[str, Any]], Coroutine[Any, Any, None]]
OnLapCallback = Callable[[NormalizedLap], Coroutine[Any, Any, None]]
OnFrameCallback = Callable[[NormalizedFrame], Coroutine[Any, Any, None]]


class _F1Protocol(asyncio.DatagramProtocol):
    """asyncio DatagramProtocol that decodes F1 24 packets."""

    def __init__(self, listener: F1UDPListener) -> None:
        self._listener = listener

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Called by asyncio when a UDP packet arrives."""
        try:
            header, decoded = decode_packet(data)
            if decoded is not None:
                asyncio.ensure_future(self._listener._handle_packet(header, decoded))
        except Exception as exc:
            logger.warning("Failed to decode packet from %s: %s", addr, exc)


class F1UDPListener:
    """Async UDP listener for F1 24 game telemetry.

    Maintains per-session state to combine data from multiple packet types
    into complete NormalizedLap and NormalizedFrame objects.

    Args:
        host: UDP bind address (default "0.0.0.0")
        port: UDP port (default 20777; use 0 for random port in tests)
        on_packet: Called for every decoded packet (header, data)
        on_lap: Called when a complete lap can be assembled
        on_frame: Called for each telemetry frame (player car only)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 20777,
        on_packet: OnPacketCallback | None = None,
        on_lap: OnLapCallback | None = None,
        on_frame: OnFrameCallback | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._on_packet = on_packet
        self._on_lap = on_lap
        self._on_frame = on_frame

        self._transport: asyncio.DatagramTransport | None = None

        # State assembled across packet types
        self._session_info: dict[str, Any] = {}
        self._participants: list[dict[str, Any]] = []
        self._car_status: list[dict[str, Any]] = []
        self._lap_data: list[dict[str, Any]] = []
        self._motion_data: list[dict[str, Any]] = []
        self._telemetry_data: list[dict[str, Any]] = []
        self._player_index: int = 0
        self._last_lap_num: int = -1

    async def start(self) -> tuple[asyncio.DatagramTransport, int]:
        """Start listening for UDP packets.

        Returns:
            Tuple of (transport, actual_port) -- actual_port is useful when port=0
        """
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _F1Protocol(self),
            local_addr=(self._host, self._port),
        )
        self._transport = transport

        # Get actual bound port (important when port=0)
        actual_port = transport.get_extra_info("sockname")[1]
        logger.info("F1 UDP listener started on %s:%d", self._host, actual_port)
        return transport, actual_port

    def stop(self) -> None:
        """Stop the UDP listener."""
        if self._transport:
            self._transport.close()
            self._transport = None
            logger.info("F1 UDP listener stopped")

    async def _handle_packet(self, header: F1PacketHeader, data: dict[str, Any]) -> None:
        """Process a decoded packet -- update state and fire callbacks."""
        self._player_index = header.player_car_index

        # Fire generic packet callback
        if self._on_packet:
            await self._on_packet(header, data)

        # Update state based on packet type
        if header.packet_id == 1:  # Session
            track_id = data.get("track_id", -1)
            self._session_info = {
                "circuit_id": TRACK_MAP.get(track_id, f"track_{track_id}"),
                "session_type": self._map_session_type(data.get("session_type", 0)),
                "track_temperature": data.get("track_temperature"),
                "air_temperature": data.get("air_temperature"),
                "total_laps": data.get("total_laps"),
            }

        elif header.packet_id == 4:  # Participants
            self._participants = data.get("participants", [])

        elif header.packet_id == 7:  # Car Status
            self._car_status = data.get("cars", [])

        elif header.packet_id == 2:  # Lap Data
            self._lap_data = data.get("cars", [])
            # Check if player completed a new lap
            if self._on_lap and self._lap_data:
                await self._try_emit_lap(header)

        elif header.packet_id == 0:  # Motion
            self._motion_data = data.get("cars", [])
            # Emit frame if we also have telemetry
            if self._on_frame and self._telemetry_data:
                await self._emit_frame(header)

        elif header.packet_id == 6:  # Car Telemetry
            self._telemetry_data = data.get("cars", [])
            # Emit frame if we also have motion
            if self._on_frame and self._motion_data:
                await self._emit_frame(header)

    async def _try_emit_lap(self, header: F1PacketHeader) -> None:
        """Attempt to assemble and emit a NormalizedLap for the player car."""
        if not self._lap_data or not self._car_status:
            return

        idx = self._player_index
        if idx >= len(self._lap_data) or idx >= len(self._car_status):
            return

        lap = self._lap_data[idx]
        current_lap = lap.get("current_lap_num", 0)

        # Only emit when we see a new lap number (avoids duplicates)
        if current_lap <= self._last_lap_num:
            return
        self._last_lap_num = current_lap

        # Build the combined packet dict for the normalizer
        participant = self._participants[idx] if idx < len(self._participants) else {}
        status = self._car_status[idx]

        combined = {
            "header": {
                "session_uid": header.session_uid,
                "frame_identifier": header.frame_identifier,
            },
            "lap_data": lap,
            "car_status": {
                "tyre_compound_visual": status.get("visual_tyre_compound", 0),
                "tyres_age_laps": status.get("tyres_age_laps", 0),
                "fuel_in_tank": status.get("fuel_in_tank", 0.0),
                "ers_deploy_mode": status.get("ers_deploy_mode", 0),
            },
            "participants": {
                "driver_id": participant.get("driver_id", 0),
                "name": participant.get("name", "Player"),
                "team_id": participant.get("team_id", 0),
            },
            "session_info": self._session_info,
        }

        try:
            normalized = normalize_f1_udp_lap(combined)
            await self._on_lap(normalized)
        except Exception as exc:
            logger.warning("Failed to normalize lap: %s", exc)

    async def _emit_frame(self, header: F1PacketHeader) -> None:
        """Assemble and emit a NormalizedFrame for the player car."""
        idx = self._player_index

        if idx >= len(self._telemetry_data) or idx >= len(self._motion_data):
            return

        tel = self._telemetry_data[idx]
        mot = self._motion_data[idx]

        frame = NormalizedFrame(
            timestamp_ms=int(header.session_time * 1000),
            speed_kph=float(tel.get("speed", 0)),
            throttle_pct=float(tel.get("throttle", 0)) * 100.0,
            brake_pct=float(tel.get("brake", 0)) * 100.0,
            steering=float(tel.get("steer", 0)),
            gear=int(tel.get("gear", 0)),
            rpm=int(tel.get("engine_rpm", 0)),
            drs=int(tel.get("drs", 0)),
            pos_x=float(mot.get("world_position_x", 0)),
            pos_y=float(mot.get("world_position_y", 0)),
            pos_z=float(mot.get("world_position_z", 0)),
            g_lat=float(mot.get("g_force_lateral", 0)),
            g_lon=float(mot.get("g_force_longitudinal", 0)),
            tire_temp_fl=float(tel.get("tyres_surface_temperature", [0, 0, 0, 0])[0]),
            tire_temp_fr=float(tel.get("tyres_surface_temperature", [0, 0, 0, 0])[1]),
            tire_temp_rl=float(tel.get("tyres_surface_temperature", [0, 0, 0, 0])[2]),
            tire_temp_rr=float(tel.get("tyres_surface_temperature", [0, 0, 0, 0])[3]),
            brake_temp_fl=float(tel.get("brakes_temperature", [0, 0, 0, 0])[0]),
            brake_temp_fr=float(tel.get("brakes_temperature", [0, 0, 0, 0])[1]),
            brake_temp_rl=float(tel.get("brakes_temperature", [0, 0, 0, 0])[2]),
            brake_temp_rr=float(tel.get("brakes_temperature", [0, 0, 0, 0])[3]),
        )

        try:
            await self._on_frame(frame)
        except Exception as exc:
            logger.warning("Failed to emit frame: %s", exc)

    @staticmethod
    def _map_session_type(code: int) -> str:
        """Map F1 24 session type code to string."""
        return {
            0: "unknown",
            1: "fp1",
            2: "fp2",
            3: "fp3",
            4: "short_practice",
            5: "qualifying_q1",
            6: "qualifying_q2",
            7: "qualifying_q3",
            8: "short_qualifying",
            9: "osq",
            10: "race",
            11: "race2",
            12: "race3",
            13: "time_trial",
        }.get(code, f"unknown_{code}")
