-- TimescaleDB Setup for GALILEO Platform
-- Configure hypertables, compression, and retention for time-series data

-- ============================================================================
-- Enable Extensions
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Satellite Telemetry Hypertable
-- ============================================================================

CREATE TABLE IF NOT EXISTS satellite_telemetry (
    timestamp           TIMESTAMPTZ NOT NULL,
    satellite_id        TEXT NOT NULL,
    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL,
    altitude_m          DOUBLE PRECISION NOT NULL,
    velocity_x          DOUBLE PRECISION,
    velocity_y          DOUBLE PRECISION,
    velocity_z          DOUBLE PRECISION,
    temperature_c       DOUBLE PRECISION,
    battery_percent     SMALLINT,
    signal_strength_db  DOUBLE PRECISION,
    raw_data            JSONB,
    PRIMARY KEY (timestamp, satellite_id)
);

-- Create hypertable with 1-day chunks
SELECT create_hypertable(
    'satellite_telemetry',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Add space partitioning by satellite_id
SELECT add_dimension(
    'satellite_telemetry',
    'satellite_id',
    number_partitions => 4,
    if_not_exists => TRUE
);

-- Compression policy (compress data older than 7 days)
ALTER TABLE satellite_telemetry SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'satellite_id',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('satellite_telemetry', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy (drop data older than 2 years)
SELECT add_retention_policy('satellite_telemetry', INTERVAL '2 years', if_not_exists => TRUE);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_satellite_telemetry_satellite ON satellite_telemetry (satellite_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_satellite_telemetry_location ON satellite_telemetry USING GIST (
    ll_to_earth(latitude, longitude)
);

-- ============================================================================
-- Gravity Measurements Hypertable
-- ============================================================================

CREATE TABLE IF NOT EXISTS gravity_measurements (
    timestamp           TIMESTAMPTZ NOT NULL,
    measurement_id      UUID NOT NULL DEFAULT uuid_generate_v4(),
    satellite_id        TEXT NOT NULL,
    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL,
    gravity_anomaly_mgal DOUBLE PRECISION NOT NULL,
    geoid_height_m      DOUBLE PRECISION,
    uncertainty         DOUBLE PRECISION,
    quality_flag        SMALLINT DEFAULT 1,
    processing_version  TEXT,
    metadata            JSONB,
    PRIMARY KEY (timestamp, measurement_id)
);

SELECT create_hypertable(
    'gravity_measurements',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

ALTER TABLE gravity_measurements SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'satellite_id',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('gravity_measurements', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('gravity_measurements', INTERVAL '10 years', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_gravity_satellite_time ON gravity_measurements (satellite_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_gravity_location ON gravity_measurements (latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_gravity_quality ON gravity_measurements (quality_flag) WHERE quality_flag = 1;

-- ============================================================================
-- API Metrics Hypertable (for tracking API performance)
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_metrics (
    timestamp       TIMESTAMPTZ NOT NULL,
    endpoint        TEXT NOT NULL,
    method          TEXT NOT NULL,
    status_code     SMALLINT NOT NULL,
    duration_ms     DOUBLE PRECISION NOT NULL,
    user_id         TEXT,
    correlation_id  TEXT,
    error_message   TEXT,
    PRIMARY KEY (timestamp, endpoint, method)
);

SELECT create_hypertable(
    'api_metrics',
    'timestamp',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

ALTER TABLE api_metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'endpoint',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('api_metrics', INTERVAL '1 day', if_not_exists => TRUE);
SELECT add_retention_policy('api_metrics', INTERVAL '90 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_api_metrics_endpoint ON api_metrics (endpoint, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_metrics_status ON api_metrics (status_code, timestamp DESC) WHERE status_code >= 400;

-- ============================================================================
-- Continuous Aggregates (Pre-computed views for fast queries)
-- ============================================================================

-- Hourly satellite telemetry summary
CREATE MATERIALIZED VIEW IF NOT EXISTS satellite_telemetry_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS hour,
    satellite_id,
    AVG(altitude_m) AS avg_altitude,
    MIN(altitude_m) AS min_altitude,
    MAX(altitude_m) AS max_altitude,
    AVG(temperature_c) AS avg_temperature,
    AVG(battery_percent) AS avg_battery,
    COUNT(*) AS sample_count
FROM satellite_telemetry
GROUP BY hour, satellite_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('satellite_telemetry_hourly',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily gravity field summary
CREATE MATERIALIZED VIEW IF NOT EXISTS gravity_daily_summary
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS day,
    satellite_id,
    AVG(gravity_anomaly_mgal) AS avg_anomaly,
    STDDEV(gravity_anomaly_mgal) AS stddev_anomaly,
    AVG(uncertainty) AS avg_uncertainty,
    COUNT(*) AS measurement_count,
    COUNT(*) FILTER (WHERE quality_flag = 1) AS good_quality_count
FROM gravity_measurements
GROUP BY day, satellite_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('gravity_daily_summary',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- API performance hourly summary
CREATE MATERIALIZED VIEW IF NOT EXISTS api_metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS hour,
    endpoint,
    method,
    COUNT(*) AS request_count,
    AVG(duration_ms) AS avg_duration,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50_duration,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_duration,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms) AS p99_duration,
    COUNT(*) FILTER (WHERE status_code >= 400) AS error_count,
    COUNT(*) FILTER (WHERE status_code >= 500) AS server_error_count
FROM api_metrics
GROUP BY hour, endpoint, method
WITH NO DATA;

SELECT add_continuous_aggregate_policy('api_metrics_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE
);

-- ============================================================================
-- Useful Views for Operations
-- ============================================================================

-- Recent SLO compliance view
CREATE OR REPLACE VIEW slo_compliance_24h AS
SELECT
    endpoint,
    method,
    SUM(request_count) AS total_requests,
    SUM(error_count) AS total_errors,
    ROUND(100.0 * (1 - SUM(error_count)::numeric / NULLIF(SUM(request_count), 0)), 4) AS availability_pct,
    AVG(p99_duration) AS avg_p99_ms,
    MAX(p99_duration) AS max_p99_ms
FROM api_metrics_hourly
WHERE hour > NOW() - INTERVAL '24 hours'
GROUP BY endpoint, method
ORDER BY total_requests DESC;

-- Active satellites view (telemetry in last hour)
CREATE OR REPLACE VIEW active_satellites AS
SELECT DISTINCT
    satellite_id,
    MAX(timestamp) AS last_seen,
    EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) AS seconds_since_last
FROM satellite_telemetry
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY satellite_id;

-- ============================================================================
-- Monitoring queries
-- ============================================================================

-- Function to get chunk information
CREATE OR REPLACE FUNCTION get_chunk_stats(table_name TEXT)
RETURNS TABLE (
    chunk_name TEXT,
    chunk_size BIGINT,
    is_compressed BOOLEAN,
    row_count BIGINT
) AS $$
BEGIN
    RETURN QUERY EXECUTE format($f$
        SELECT
            c.chunk_name::TEXT,
            pg_total_relation_size(format('%%I.%%I', c.chunk_schema, c.chunk_name)::regclass) AS chunk_size,
            c.is_compressed,
            (SELECT count(*) FROM %%I.%%I) AS row_count
        FROM timescaledb_information.chunks c
        WHERE c.hypertable_name = %L
        ORDER BY c.range_end DESC
    $f$, table_name)
    USING table_name;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Grants
-- ============================================================================

GRANT SELECT ON satellite_telemetry, gravity_measurements, api_metrics TO galileo;
GRANT INSERT ON satellite_telemetry, gravity_measurements, api_metrics TO galileo;
GRANT SELECT ON satellite_telemetry_hourly, gravity_daily_summary, api_metrics_hourly TO galileo;
GRANT SELECT ON slo_compliance_24h, active_satellites TO galileo;

-- ============================================================================
-- Maintenance Job - Statistics
-- ============================================================================

-- Run ANALYZE on hypertables periodically
SELECT add_job(
    proc => $$ANALYZE satellite_telemetry$$,
    schedule_interval => INTERVAL '6 hours',
    if_not_exists => TRUE
);

SELECT add_job(
    proc => $$ANALYZE gravity_measurements$$,
    schedule_interval => INTERVAL '6 hours',
    if_not_exists => TRUE
);

SELECT add_job(
    proc => $$ANALYZE api_metrics$$,
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Done!
SELECT 'TimescaleDB setup complete' AS status,
       (SELECT count(*) FROM timescaledb_information.hypertables) AS hypertables,
       (SELECT count(*) FROM timescaledb_information.continuous_aggregates) AS continuous_aggregates;
