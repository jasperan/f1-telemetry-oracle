"""Raw byte fixtures for F1 24 UDP packets.

Each fixture is the minimum valid binary representation of a packet type.
The F1 24 packet header is 29 bytes:
  - uint16  packetFormat      (2024)
  - uint8   gameYear          (24)
  - uint8   gameMajorVersion
  - uint8   gameMinorVersion
  - uint8   packetVersion
  - uint8   packetId          (identifies packet type)
  - uint64  sessionUID
  - float   sessionTime
  - uint32  frameIdentifier
  - uint32  overallFrameIdentifier
  - uint8   playerCarIndex
  - uint8   secondaryPlayerCarIndex
"""

import struct

# F1 24 header format: '<HBBBBBQfIIBB' = 29 bytes
HEADER_FORMAT = "<HBBBBBQfIIBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 29 bytes


def _make_header(packet_id: int, session_uid: int = 123456789, player_car_index: int = 0) -> bytes:
    """Build a valid F1 24 packet header."""
    return struct.pack(
        HEADER_FORMAT,
        2024,  # packetFormat
        24,  # gameYear
        1,  # gameMajorVersion
        12,  # gameMinorVersion
        1,  # packetVersion
        packet_id,  # packetId
        session_uid,
        42.5,  # sessionTime (float)
        9001,  # frameIdentifier
        9001,  # overallFrameIdentifier
        player_car_index,
        255,  # secondaryPlayerCarIndex (255 = none)
    )


def make_motion_packet() -> bytes:
    """Packet ID 0: Motion Data — 22 cars, each 60 bytes.

    CarMotionData (per car):
      float worldPositionX, Y, Z (12 bytes)
      float worldVelocityX, Y, Z (12 bytes)
      int16 worldForwardDirX, Y, Z (6 bytes)
      int16 worldRightDirX, Y, Z (6 bytes)
      float gForceLateral, gForceLongitudinal, gForceVertical (12 bytes)
      float yaw, pitch, roll (12 bytes)
    Total per car: 60 bytes
    """
    header = _make_header(packet_id=0)
    # 22 cars * 60 bytes each = 1320 bytes of car motion data
    car_data = b""
    for i in range(22):
        car_data += struct.pack(
            "<ffffff3h3hffffff",
            100.0 + i,
            0.5,
            200.0 + i,  # pos X, Y, Z
            50.0,
            0.0,
            30.0,  # vel X, Y, Z
            1000,
            0,
            0,  # forward dir
            0,
            0,
            1000,  # right dir
            0.5 if i == 0 else 0.1,  # gForceLateral
            1.2 if i == 0 else 0.3,  # gForceLongitudinal
            1.0,  # gForceVertical
            0.0,
            0.0,
            0.0,  # yaw, pitch, roll
        )
    return header + car_data


def make_session_packet() -> bytes:
    """Packet ID 1: Session Data.

    Simplified — we only decode the first few critical fields:
      uint8  weather
      int8   trackTemperature
      int8   airTemperature
      uint8  totalLaps
      uint16 trackLength
      uint8  sessionType (0=unknown,5=Q,10=R,etc.)
      int8   trackId
      uint8  formula
      ... (many more fields, padded with zeros)
    """
    header = _make_header(packet_id=1)
    session_data = struct.pack(
        "<BbbBHBbB",
        0,  # weather (clear)
        38,  # trackTemperature
        25,  # airTemperature
        53,  # totalLaps
        5793,  # trackLength (Monza)
        10,  # sessionType (10=Race)
        14,  # trackId (14=Monza)
        0,  # formula (0=F1 Modern)
    )
    # Pad to reasonable packet size
    session_data += b"\x00" * 600
    return header + session_data


def make_lap_data_packet() -> bytes:
    """Packet ID 2: Lap Data — 22 cars, each 57 bytes (F1 24 format).

    LapData (per car):
      uint32 lastLapTimeInMS
      uint32 currentLapTimeInMS
      uint16 sector1TimeInMS
      uint16 sector1TimeMinutes
      uint16 sector2TimeInMS
      uint16 sector2TimeMinutes
      uint16 deltaToBestLapInMS (unused here)
      uint16 deltaToRaceLeaderInMS (unused here)
      float  lapDistance
      float  totalDistance
      float  safetyCarDelta
      uint8  carPosition
      uint8  currentLapNum
      uint8  pitStatus
      uint8  numPitStops
      uint8  sector
      uint8  currentLapInvalid
      uint8  penalties
      uint8  totalWarnings
      uint8  cornerCuttingWarnings
      uint8  numUnservedDriveThroughPens
      uint8  numUnservedStopGoPens
      uint8  gridPosition
      uint8  driverStatus
      uint8  resultStatus
      uint8  pitLaneTimerActive
      uint16 pitLaneTimeInLaneInMS
      uint16 pitStopTimerInMS
      uint8  pitStopShouldServePen
      float  speedTrapFastestSpeed
      uint8  speedTrapFastestLap
    Total: 57 bytes per car
    """
    header = _make_header(packet_id=2)
    car_data = b""
    for i in range(22):
        is_player = i == 0
        car_data += struct.pack(
            "<IIHHHHHHfffBBBBBBBBBBBBBBBHHBfB",
            86000 if is_player else 87000,  # lastLapTimeInMS
            42000,  # currentLapTimeInMS
            28512 if is_player else 29000,  # sector1TimeInMS
            0,  # sector1TimeMinutes
            33180 if is_player else 33500,  # sector2TimeInMS
            0,  # sector2TimeMinutes
            0,  # deltaToBestLap
            0,  # deltaToRaceLeader
            2500.0,  # lapDistance
            15000.0,  # totalDistance
            0.0,  # safetyCarDelta
            i + 1,  # carPosition
            5 if is_player else 4,  # currentLapNum
            0,  # pitStatus
            0,  # numPitStops
            2,  # sector (0-indexed)
            0 if is_player else 0,  # currentLapInvalid
            0,  # penalties
            0,  # totalWarnings
            0,  # cornerCuttingWarnings
            0,  # numUnservedDriveThrough
            0,  # numUnservedStopGo
            i + 1,  # gridPosition
            1,  # driverStatus (1=active)
            2,  # resultStatus (2=active)
            0,  # pitLaneTimerActive
            0,  # pitLaneTimeInLane
            0,  # pitStopTimer
            0,  # pitStopShouldServePen
            342.5 if is_player else 340.0,  # speedTrapFastestSpeed
            3,  # speedTrapFastestLap
        )
    return header + car_data


def make_car_telemetry_packet() -> bytes:
    """Packet ID 6: Car Telemetry — 22 cars, each 60 bytes.

    CarTelemetryData (per car):
      uint16 speed
      float  throttle
      float  steer
      float  brake
      uint8  clutch
      int8   gear
      uint16 engineRPM
      uint8  drs
      uint8  revLightsPercent
      uint16 revLightsBitValue
      uint16[4] brakesTemperature (FL,FR,RL,RR)
      uint8[4]  tyresSurfaceTemperature (FL,FR,RL,RR)
      uint8[4]  tyresInnerTemperature (FL,FR,RL,RR)
      uint16 engineTemperature
      float[4] tyresPressure (FL,FR,RL,RR)
      uint8[4] surfaceType
    Total: 60 bytes per car
    """
    header = _make_header(packet_id=6)
    car_data = b""
    for i in range(22):
        is_player = i == 0
        car_data += struct.pack(
            "<HfffBbHBBH4H4B4BH4f4B",
            320 if is_player else 310,  # speed
            1.0 if is_player else 0.9,  # throttle
            -0.05,  # steer
            0.0,  # brake
            0,  # clutch
            8 if is_player else 7,  # gear (signed: -1=R, 0=N, 1-8)
            12500 if is_player else 12000,  # engineRPM
            1 if is_player else 0,  # drs
            80,  # revLightsPercent
            0,  # revLightsBitValue
            800,
            810,
            780,
            790,  # brakesTemperature
            105,
            107,
            100,
            102,  # tyresSurfaceTemperature
            110,
            112,
            105,
            107,  # tyresInnerTemperature
            110,  # engineTemperature
            23.5,
            23.5,
            21.0,
            21.0,  # tyresPressure
            0,
            0,
            0,
            0,  # surfaceType
        )
    return header + car_data


def make_car_status_packet() -> bytes:
    """Packet ID 7: Car Status — 22 cars, each ~55 bytes.

    Key fields:
      uint8  tractionControl
      uint8  antiLockBrakes
      uint8  fuelMix
      uint8  frontBrakeBias
      uint8  pitLimiterStatus
      float  fuelInTank
      float  fuelCapacity
      float  fuelRemainingLaps
      uint16 maxRPM
      uint16 idleRPM
      uint8  maxGears
      uint8  drsAllowed
      uint16 drsActivationDistance
      uint8  actualTyreCompound
      uint8  visualTyreCompound
      uint8  tyresAgeLaps
      int8   vehicleFiaFlags
      float  enginePowerICE
      float  enginePowerMGUK
      float  ersStoreEnergy
      uint8  ersDeployMode
      float  ersHarvestedThisLapMGUK
      float  ersHarvestedThisLapMGUH
      float  ersDeployedThisLap
      uint8  networkPaused
    """
    header = _make_header(packet_id=7)
    car_data = b""
    for i in range(22):
        is_player = i == 0
        car_data += struct.pack(
            "<BBBBBfffHHBBHBBBbffffBfffB",
            1,  # tractionControl
            1,  # antiLockBrakes
            2,  # fuelMix (2=standard)
            56,  # frontBrakeBias
            0,  # pitLimiterStatus
            42.5 if is_player else 40.0,  # fuelInTank
            110.0,  # fuelCapacity
            15.5,  # fuelRemainingLaps
            13000,  # maxRPM
            3500,  # idleRPM
            8,  # maxGears
            1,  # drsAllowed
            200,  # drsActivationDistance
            18,  # actualTyreCompound (C3)
            16 if is_player else 17,  # visualTyreCompound (16=SOFT, 17=MEDIUM)
            3 if is_player else 5,  # tyresAgeLaps
            0,  # vehicleFiaFlags
            750.0,  # enginePowerICE
            120.0,  # enginePowerMGUK
            2000000.0,  # ersStoreEnergy
            0.75,  # ersDeployPct
            3,  # ersDeployMode
            100000.0,  # ersHarvestedMGUK
            200000.0,  # ersHarvestedMGUH
            150000.0,  # ersDeployedThisLap
            0,  # networkPaused
        )
    return header + car_data


def make_participants_packet() -> bytes:
    """Packet ID 4: Participants — header + uint8 numActiveCars + 22 * ParticipantData.

    ParticipantData (per car, 56 bytes):
      uint8   aiControlled
      uint8   driverId
      uint8   networkId
      uint8   teamId
      uint8   myTeam
      uint8   raceNumber
      uint8   nationality
      char[48] name (null-terminated)
      uint8   yourTelemetry
      uint8   showOnlineNames
      uint16  techLevel
      uint8   platform
    """
    header = _make_header(packet_id=4)
    num_cars = struct.pack("<B", 22)

    car_data = b""
    names = [
        "Player",
        "Verstappen",
        "Leclerc",
        "Norris",
        "Sainz",
        "Hamilton",
        "Russell",
        "Piastri",
        "Alonso",
        "Stroll",
        "Gasly",
        "Ocon",
        "Tsunoda",
        "Ricciardo",
        "Bottas",
        "Zhou",
        "Magnussen",
        "Hulkenberg",
        "Albon",
        "Sargeant",
        "De Vries",
        "Lawson",
    ]
    for i in range(22):
        name_bytes = names[i].encode("utf-8")[:47].ljust(48, b"\x00")
        car_data += struct.pack(
            "<BBBBBBB",
            0 if i == 0 else 1,  # aiControlled (0=human player)
            i,  # driverId
            255,  # networkId
            i % 10,  # teamId
            0,  # myTeam
            i + 1,  # raceNumber
            0,  # nationality
        )
        car_data += name_bytes
        car_data += struct.pack("<BBHB", 1, 1, 0, 0)

    return header + num_cars + car_data
