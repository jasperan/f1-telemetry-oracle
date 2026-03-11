"""Test F1 24 async UDP listener -- send packets to localhost, verify decode + normalize."""

import asyncio

import pytest

from collectors.f1_udp.decoder import F1PacketHeader
from collectors.f1_udp.listener import F1UDPListener
from collectors.normalizer import NormalizedFrame, NormalizedLap
from tests.fixtures.f1_24_packets import (
    make_car_status_packet,
    make_car_telemetry_packet,
    make_lap_data_packet,
    make_motion_packet,
    make_participants_packet,
    make_session_packet,
)


async def _send_packet(raw: bytes, port: int) -> None:
    """Send a raw UDP packet to the listener on localhost."""
    loop = asyncio.get_event_loop()
    transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol,
        remote_addr=("127.0.0.1", port),
    )
    transport.sendto(raw)
    transport.close()


class TestF1UDPListener:
    @pytest.mark.asyncio
    async def test_receive_and_decode_packets(self):
        """Send raw UDP packets to the listener and verify they are decoded."""
        received_packets: list[tuple[F1PacketHeader, dict]] = []

        async def on_packet(header: F1PacketHeader, data: dict) -> None:
            received_packets.append((header, data))

        listener = F1UDPListener(host="127.0.0.1", port=0, on_packet=on_packet)
        transport, port = await listener.start()

        try:
            # Send test packets
            for make_fn in [
                make_motion_packet,
                make_session_packet,
                make_lap_data_packet,
                make_participants_packet,
                make_car_telemetry_packet,
                make_car_status_packet,
            ]:
                raw = make_fn()
                await _send_packet(raw, port)

            # Wait for packets to be processed
            await asyncio.sleep(0.3)

            assert len(received_packets) == 6

            # Verify packet types
            packet_ids = [h.packet_id for h, _ in received_packets]
            assert 0 in packet_ids  # motion
            assert 1 in packet_ids  # session
            assert 2 in packet_ids  # lap data
            assert 4 in packet_ids  # participants
            assert 6 in packet_ids  # car telemetry
            assert 7 in packet_ids  # car status
        finally:
            listener.stop()

    @pytest.mark.asyncio
    async def test_normalize_lap_from_combined_packets(self):
        """Listener assembles NormalizedLap from lap_data + car_status + participants + session."""
        laps_received: list[NormalizedLap] = []

        async def on_lap(lap: NormalizedLap) -> None:
            laps_received.append(lap)

        listener = F1UDPListener(host="127.0.0.1", port=0, on_lap=on_lap)
        transport, port = await listener.start()

        try:
            # Send the packets needed to assemble a lap
            # Order matters: session + participants + car_status must come before lap_data
            for make_fn in [
                make_session_packet,
                make_participants_packet,
                make_car_status_packet,
                make_lap_data_packet,
            ]:
                raw = make_fn()
                await _send_packet(raw, port)
                # Small delay to ensure ordering
                await asyncio.sleep(0.05)

            await asyncio.sleep(0.3)

            # After receiving all packet types, listener should emit a normalized lap
            assert len(laps_received) >= 1

            lap = laps_received[0]
            assert isinstance(lap, NormalizedLap)
            assert lap.source == "sim"
            assert lap.lap_number == 5
            assert lap.sector1_ms == 28512
            assert lap.sector2_ms == 33180
            assert lap.lap_time_ms == 86000
            assert lap.tire_compound == "SOFT"
            assert lap.tire_age_laps == 3
            assert abs(lap.fuel_load_kg - 42.5) < 0.01
        finally:
            listener.stop()

    @pytest.mark.asyncio
    async def test_normalize_frame_from_telemetry(self):
        """Listener produces NormalizedFrame from car_telemetry + motion packets."""
        frames_received: list[NormalizedFrame] = []

        async def on_frame(frame: NormalizedFrame) -> None:
            frames_received.append(frame)

        listener = F1UDPListener(host="127.0.0.1", port=0, on_frame=on_frame)
        transport, port = await listener.start()

        try:
            # Send motion first, then telemetry (frame emitted when both are present)
            await _send_packet(make_motion_packet(), port)
            await asyncio.sleep(0.05)
            await _send_packet(make_car_telemetry_packet(), port)

            await asyncio.sleep(0.3)

            assert len(frames_received) >= 1
            frame = frames_received[0]
            assert isinstance(frame, NormalizedFrame)
            assert frame.speed_kph == 320
            assert abs(frame.throttle_pct - 100.0) < 0.1
            assert frame.gear == 8
            assert frame.rpm == 12500
        finally:
            listener.stop()
