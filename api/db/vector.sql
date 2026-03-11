-- F1 Telemetry Oracle — Vector Search Index
-- Creates a vector index on LAPS.lap_embedding for similarity search
-- Requires Oracle 26ai Free (23ai+ for AI Vector Search)

-- ============================================================
-- Drop existing vector index (idempotent)
-- ============================================================
BEGIN
   EXECUTE IMMEDIATE 'DROP INDEX idx_laps_embedding';
EXCEPTION
   WHEN OTHERS THEN
       IF SQLCODE != -1418 THEN RAISE; END IF;
END;
/

-- ============================================================
-- Create vector index using COSINE distance
-- IVF (Inverted File) index for approximate nearest neighbor
-- Parameters:
--   DISTANCE: COSINE (normalized vectors, range 0-2)
--   TYPE: IVF — good for medium-sized datasets (thousands to millions)
--   NEIGHBOR PARTITIONS: auto-tuned by Oracle
--
-- Note: If the table has very few rows, Oracle may reject the index
-- creation. The VECTOR_DISTANCE function still works without an
-- index (exact scan). The index accelerates queries at scale.
-- ============================================================
BEGIN
    EXECUTE IMMEDIATE '
        CREATE VECTOR INDEX idx_laps_embedding
        ON laps(lap_embedding)
        ORGANIZATION NEIGHBOR PARTITIONS
        DISTANCE COSINE
        WITH TARGET ACCURACY 95
    ';
EXCEPTION
    WHEN OTHERS THEN
        -- ORA-51956: insufficient data for vector index
        -- ORA-51957: cannot create vector index on empty table
        -- Let these pass silently — exact scan still works
        IF SQLCODE NOT IN (-51956, -51957) THEN RAISE; END IF;
END;
/
