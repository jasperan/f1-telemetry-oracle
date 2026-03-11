-- F1 Telemetry Oracle — JSON Relational Duality Views
-- Requires Oracle 26ai Free (23ai+ for duality view support)

-- ============================================================
-- Drop existing views (idempotent)
-- ============================================================
BEGIN
   FOR v IN (
       SELECT view_name FROM user_views
       WHERE view_name IN ('LAP_DV', 'SESSION_DV')
   ) LOOP
       EXECUTE IMMEDIATE 'DROP VIEW ' || v.view_name;
   END LOOP;
END;
/

-- ============================================================
-- LAP_DV — Insert/update laps as JSON documents
-- _id maps to the primary key (lap_id)
-- ============================================================
CREATE JSON RELATIONAL DUALITY VIEW lap_dv AS
    laps @insert @update @delete
    {
        _id          : lap_id,
        session_id   : session_id,
        driver_id    : driver_id,
        lap_number   : lap_number,
        sector1_ms   : sector1_ms,
        sector2_ms   : sector2_ms,
        sector3_ms   : sector3_ms,
        lap_time_ms  : lap_time_ms,
        tire_compound: tire_compound,
        tire_age_laps: tire_age_laps,
        fuel_load_kg : fuel_load_kg,
        ers_deploy_pct: ers_deploy_pct,
        is_valid     : is_valid,
        position     : position,
        created_at   : created_at
    };

-- ============================================================
-- SESSION_DV — Read sessions with nested circuit info
-- _id maps to the primary key (session_id)
-- ============================================================
CREATE JSON RELATIONAL DUALITY VIEW session_dv AS
    sessions @insert @update @delete
    {
        _id          : session_id,
        session_type : session_type,
        source       : source,
        season       : season,
        round_number : round_number,
        air_temp_c   : air_temp_c,
        track_temp_c : track_temp_c,
        started_at   : started_at,
        created_at   : created_at,
        circuit      : circuits
        {
            circuit_id   : circuit_id,
            circuit_name : circuit_name,
            country      : country,
            locality     : locality
        }
    };
