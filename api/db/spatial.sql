-- F1 Telemetry Oracle — Spatial Configuration
-- Since MDSYS.SDO_GEOMETRY is not available in Oracle Free slim,
-- we use JSON-based geometry with a PL/SQL Haversine distance function
-- and a compound index on lat/lng for proximity queries.

-- ============================================================
-- Haversine distance function (returns km between two GPS points)
-- ============================================================
CREATE OR REPLACE FUNCTION haversine_km(
    lat1 IN NUMBER, lng1 IN NUMBER,
    lat2 IN NUMBER, lng2 IN NUMBER
) RETURN NUMBER IS
    v_R      CONSTANT NUMBER := 6371;  -- Earth radius in km
    v_dlat   NUMBER;
    v_dlng   NUMBER;
    v_a      NUMBER;
    v_c      NUMBER;
BEGIN
    v_dlat := (lat2 - lat1) * 3.14159265358979 / 180;
    v_dlng := (lng2 - lng1) * 3.14159265358979 / 180;
    v_a := SIN(v_dlat / 2) * SIN(v_dlat / 2)
          + COS(lat1 * 3.14159265358979 / 180) * COS(lat2 * 3.14159265358979 / 180)
          * SIN(v_dlng / 2) * SIN(v_dlng / 2);
    v_c := 2 * ATAN2(SQRT(v_a), SQRT(1 - v_a));
    RETURN v_R * v_c;
END;
/

-- ============================================================
-- Compound index on lat/lng for proximity searches
-- ============================================================
BEGIN
   EXECUTE IMMEDIATE 'DROP INDEX idx_circuits_lat_lng';
EXCEPTION
   WHEN OTHERS THEN
       IF SQLCODE != -1418 THEN RAISE; END IF;
END;
/

CREATE INDEX idx_circuits_lat_lng ON circuits(lat, lng);
