-- F1 Telemetry Oracle — Core Schema
-- Oracle 26ai Free — uses VECTOR, JSON, SDO_GEOMETRY types

-- ============================================================
-- Drop existing objects (idempotent re-runs)
-- ============================================================
BEGIN
   FOR t IN (
       SELECT table_name FROM user_tables
       WHERE table_name IN (
           'PREDICTIONS','PIT_STOPS','RACE_EVENTS','CAR_SETUPS',
           'TELEMETRY_FRAMES','LAPS','SESSIONS','TEAMS','DRIVERS','CIRCUITS',
           'RACE_DOCUMENTS','LAP_SECTOR_EMBEDDINGS'
       )
   ) LOOP
       EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
   END LOOP;
END;
/

-- ============================================================
-- 1. CIRCUITS
-- ============================================================
CREATE TABLE circuits (
    circuit_id     VARCHAR2(64)    NOT NULL,
    circuit_name   VARCHAR2(200)   NOT NULL,
    country        VARCHAR2(100)   NOT NULL,
    locality       VARCHAR2(100),
    track_length_m NUMBER(8,1),
    lat            NUMBER(10,6),
    lng            NUMBER(10,6),
    track_geometry JSON,
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_circuits PRIMARY KEY (circuit_id)
);

-- ============================================================
-- 2. DRIVERS
-- ============================================================
CREATE TABLE drivers (
    driver_id    VARCHAR2(64)   NOT NULL,
    code         VARCHAR2(3),
    first_name   VARCHAR2(100)  NOT NULL,
    last_name    VARCHAR2(100)  NOT NULL,
    driver_number NUMBER(3),
    nationality  VARCHAR2(100),
    is_sim_player NUMBER(1) DEFAULT 0 NOT NULL,
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_drivers PRIMARY KEY (driver_id),
    CONSTRAINT ck_drivers_sim CHECK (is_sim_player IN (0, 1))
);

-- ============================================================
-- 3. TEAMS
-- ============================================================
CREATE TABLE teams (
    team_id    VARCHAR2(64)   NOT NULL,
    team_name  VARCHAR2(200)  NOT NULL,
    color_hex  VARCHAR2(7),
    engine     VARCHAR2(100),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_teams PRIMARY KEY (team_id)
);

-- ============================================================
-- 4. SESSIONS
-- ============================================================
CREATE TABLE sessions (
    session_id    VARCHAR2(64)   NOT NULL,
    circuit_id    VARCHAR2(64)   NOT NULL,
    session_type  VARCHAR2(20)   NOT NULL,
    source        VARCHAR2(20)   NOT NULL,
    season        NUMBER(4),
    round_number  NUMBER(3),
    weather_data  JSON,
    air_temp_c    NUMBER(5,1),
    track_temp_c  NUMBER(5,1),
    started_at    TIMESTAMP,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_sessions PRIMARY KEY (session_id),
    CONSTRAINT fk_sessions_circuit FOREIGN KEY (circuit_id) REFERENCES circuits(circuit_id),
    CONSTRAINT ck_sessions_source CHECK (source IN ('sim', 'openf1', 'ergast'))
);

-- ============================================================
-- 5. LAPS
-- ============================================================
CREATE TABLE laps (
    lap_id          VARCHAR2(64)   NOT NULL,
    session_id      VARCHAR2(64)   NOT NULL,
    driver_id       VARCHAR2(64)   NOT NULL,
    lap_number      NUMBER(4)      NOT NULL,
    sector1_ms      NUMBER(10),
    sector2_ms      NUMBER(10),
    sector3_ms      NUMBER(10),
    lap_time_ms     NUMBER(10),
    tire_compound   VARCHAR2(20),
    tire_age_laps   NUMBER(4),
    fuel_load_kg    NUMBER(6,2),
    ers_deploy_pct  NUMBER(5,2),
    is_valid        NUMBER(1) DEFAULT 1 NOT NULL,
    position        NUMBER(3),
    lap_embedding   VECTOR(384, FLOAT32),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_laps PRIMARY KEY (lap_id),
    CONSTRAINT fk_laps_session FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    CONSTRAINT fk_laps_driver FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    CONSTRAINT ck_laps_valid CHECK (is_valid IN (0, 1))
);

-- ============================================================
-- 6. TELEMETRY_FRAMES
-- ============================================================
CREATE TABLE telemetry_frames (
    frame_id      VARCHAR2(64)   NOT NULL,
    lap_id        VARCHAR2(64)   NOT NULL,
    timestamp_ms  NUMBER(14)     NOT NULL,
    distance_m    NUMBER(8,2),
    speed_kph     NUMBER(5,1),
    throttle_pct  NUMBER(5,2),
    brake_pct     NUMBER(5,2),
    steering      NUMBER(8,4),
    gear          NUMBER(2),
    rpm           NUMBER(6),
    drs           NUMBER(1),
    pos_x         NUMBER(12,4),
    pos_y         NUMBER(12,4),
    pos_z         NUMBER(12,4),
    g_lat         NUMBER(8,4),
    g_lon         NUMBER(8,4),
    tire_temp_fl  NUMBER(5,1),
    tire_temp_fr  NUMBER(5,1),
    tire_temp_rl  NUMBER(5,1),
    tire_temp_rr  NUMBER(5,1),
    brake_temp_fl NUMBER(6,1),
    brake_temp_fr NUMBER(6,1),
    brake_temp_rl NUMBER(6,1),
    brake_temp_rr NUMBER(6,1),
    CONSTRAINT pk_telemetry_frames PRIMARY KEY (frame_id),
    CONSTRAINT fk_frames_lap FOREIGN KEY (lap_id) REFERENCES laps(lap_id)
);

-- ============================================================
-- 7. CAR_SETUPS
-- ============================================================
CREATE TABLE car_setups (
    setup_id         VARCHAR2(64)   NOT NULL,
    session_id       VARCHAR2(64)   NOT NULL,
    driver_id        VARCHAR2(64)   NOT NULL,
    front_wing       NUMBER(3),
    rear_wing        NUMBER(3),
    diff_on_pct      NUMBER(5,2),
    diff_off_pct     NUMBER(5,2),
    front_camber     NUMBER(6,3),
    rear_camber      NUMBER(6,3),
    front_toe        NUMBER(6,4),
    rear_toe         NUMBER(6,4),
    front_suspension NUMBER(3),
    rear_suspension  NUMBER(3),
    front_arb        NUMBER(3),
    rear_arb         NUMBER(3),
    front_ride_height NUMBER(3),
    rear_ride_height  NUMBER(3),
    brake_pressure   NUMBER(5,2),
    brake_bias_pct   NUMBER(5,2),
    fuel_load_kg     NUMBER(6,2),
    tire_pressure_fl NUMBER(5,1),
    tire_pressure_fr NUMBER(5,1),
    tire_pressure_rl NUMBER(5,1),
    tire_pressure_rr NUMBER(5,1),
    ballast          NUMBER(4),
    setup_data       JSON,
    created_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_car_setups PRIMARY KEY (setup_id),
    CONSTRAINT fk_setups_session FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    CONSTRAINT fk_setups_driver FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

-- ============================================================
-- 8. RACE_EVENTS
-- ============================================================
CREATE TABLE race_events (
    event_id     VARCHAR2(64)   NOT NULL,
    session_id   VARCHAR2(64)   NOT NULL,
    driver_id    VARCHAR2(64),
    lap_number   NUMBER(4),
    event_type   VARCHAR2(50)   NOT NULL,
    event_data   JSON,
    occurred_at  TIMESTAMP,
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_race_events PRIMARY KEY (event_id),
    CONSTRAINT fk_events_session FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    CONSTRAINT fk_events_driver FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

-- ============================================================
-- 9. PIT_STOPS
-- ============================================================
CREATE TABLE pit_stops (
    pit_id          VARCHAR2(64)   NOT NULL,
    session_id      VARCHAR2(64)   NOT NULL,
    driver_id       VARCHAR2(64)   NOT NULL,
    lap_number      NUMBER(4)      NOT NULL,
    duration_ms     NUMBER(10),
    tire_from       VARCHAR2(20),
    tire_to         VARCHAR2(20),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_pit_stops PRIMARY KEY (pit_id),
    CONSTRAINT fk_pits_session FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    CONSTRAINT fk_pits_driver FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

-- ============================================================
-- 10. PREDICTIONS
-- ============================================================
CREATE TABLE predictions (
    prediction_id  VARCHAR2(64)   NOT NULL,
    lap_id         VARCHAR2(64)   NOT NULL,
    model_name     VARCHAR2(100)  NOT NULL,
    predicted_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    prediction     JSON,
    CONSTRAINT pk_predictions PRIMARY KEY (prediction_id),
    CONSTRAINT fk_preds_lap FOREIGN KEY (lap_id) REFERENCES laps(lap_id)
);

-- ============================================================
-- 11. RACE_DOCUMENTS -- text knowledge base for RAG
-- Embedded in-database with VECTOR_EMBEDDING(ALL_MINILM_L12_V2)
-- ============================================================
CREATE TABLE race_documents (
    doc_id            VARCHAR2(64)   NOT NULL,
    doc_type          VARCHAR2(50)   NOT NULL,
    title             VARCHAR2(300),
    content           CLOB,
    content_embedding VECTOR(384, FLOAT32),
    created_at        TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_race_documents PRIMARY KEY (doc_id)
);

-- ============================================================
-- 12. LAP_SECTOR_EMBEDDINGS -- per-sector driving-style vectors
-- ============================================================
CREATE TABLE lap_sector_embeddings (
    lap_id            VARCHAR2(64)   NOT NULL,
    sector_no         NUMBER(1)      NOT NULL,
    sector_embedding  VECTOR(384, FLOAT32),
    CONSTRAINT pk_lap_sectors PRIMARY KEY (lap_id, sector_no),
    CONSTRAINT fk_lap_sectors_lap FOREIGN KEY (lap_id) REFERENCES laps(lap_id),
    CONSTRAINT ck_lap_sectors_no CHECK (sector_no IN (1, 2, 3))
);

-- ============================================================
-- Performance indexes
-- ============================================================
CREATE INDEX idx_laps_session ON laps(session_id);
CREATE INDEX idx_laps_driver ON laps(driver_id);
CREATE INDEX idx_frames_lap ON telemetry_frames(lap_id);
CREATE INDEX idx_frames_timestamp ON telemetry_frames(lap_id, timestamp_ms);
CREATE INDEX idx_events_session ON race_events(session_id);
CREATE INDEX idx_pits_session ON pit_stops(session_id);
CREATE INDEX idx_sessions_circuit ON sessions(circuit_id);
CREATE INDEX idx_sessions_source ON sessions(source);
CREATE INDEX idx_predictions_lap ON predictions(lap_id);
CREATE INDEX idx_race_docs_type ON race_documents(doc_type);
CREATE INDEX idx_lap_sectors_lap ON lap_sector_embeddings(lap_id);
