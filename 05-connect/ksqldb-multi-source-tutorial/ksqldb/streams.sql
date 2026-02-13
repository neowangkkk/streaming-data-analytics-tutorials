-- ============================================================================
-- ksqlDB Stream and Table Definitions
-- ============================================================================

-- Set processing to start from earliest available data
SET 'auto.offset.reset' = 'earliest';

-- ============================================================================
-- STREAM 1: IoT Sensor Data
-- ============================================================================

CREATE STREAM iot_sensors_raw (
    sensor_id VARCHAR,
    location VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    timestamp VARCHAR,
    temperature_celsius DOUBLE,
    humidity_percent DOUBLE,
    pressure_hpa DOUBLE,
    air_quality_index INT
) WITH (
    KAFKA_TOPIC='iot-sensors',
    VALUE_FORMAT='JSON'
);

-- Create a cleaned version with proper timestamp
CREATE STREAM iot_sensors_stream WITH (
    KAFKA_TOPIC='iot-sensors-cleaned',
    VALUE_FORMAT='JSON'
) AS SELECT
    sensor_id,
    location,
    latitude,
    longitude,
    STRINGTOTIMESTAMP(timestamp, 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z''') as event_time,
    temperature_celsius,
    humidity_percent,
    pressure_hpa,
    air_quality_index
FROM iot_sensors_raw
EMIT CHANGES;

-- ============================================================================
-- STREAM 2: Weather Data (from API)
-- ============================================================================

CREATE STREAM weather_raw (
    latitude DOUBLE,
    longitude DOUBLE,
    generationtime_ms DOUBLE,
    utc_offset_seconds INT,
    timezone VARCHAR,
    timezone_abbreviation VARCHAR,
    elevation DOUBLE,
    current_units STRUCT<
        time VARCHAR,
        interval VARCHAR,
        temperature_2m VARCHAR,
        relative_humidity_2m VARCHAR,
        wind_speed_10m VARCHAR,
        pressure_msl VARCHAR
    >,
    current STRUCT<
        time VARCHAR,
        interval INT,
        temperature_2m DOUBLE,
        relative_humidity_2m INT,
        wind_speed_10m DOUBLE,
        pressure_msl DOUBLE
    >
) WITH (
    KAFKA_TOPIC='weather-data',
    VALUE_FORMAT='JSON'
);

-- Extract and flatten weather data
CREATE STREAM weather_stream WITH (
    KAFKA_TOPIC='weather-cleaned',
    VALUE_FORMAT='JSON'
) AS SELECT
    latitude,
    longitude,
    timezone,
    current->time as observation_time,
    current->temperature_2m as temperature_celsius,
    current->relative_humidity_2m as humidity_percent,
    current->wind_speed_10m as wind_speed_kmh,
    current->pressure_msl as pressure_hpa
FROM weather_raw
EMIT CHANGES;

-- ============================================================================
-- TABLE: User Profiles (from PostgreSQL)
-- ============================================================================

CREATE STREAM users_stream (
    user_id INT,
    username VARCHAR,
    email VARCHAR,
    city VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    created_at BIGINT
) WITH (
    KAFKA_TOPIC='postgres-users',
    VALUE_FORMAT='JSON'
);

-- Create a table for lookups
CREATE TABLE users_table WITH (
    KAFKA_TOPIC='users-table',
    VALUE_FORMAT='JSON'
) AS SELECT
    user_id,
    LATEST_BY_OFFSET(username) as username,
    LATEST_BY_OFFSET(email) as email,
    LATEST_BY_OFFSET(city) as city,
    LATEST_BY_OFFSET(latitude) as latitude,
    LATEST_BY_OFFSET(longitude) as longitude
FROM users_stream
GROUP BY user_id
EMIT CHANGES;

-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Check if data is flowing
-- Run these in ksqlDB CLI to verify:

-- SELECT * FROM iot_sensors_stream EMIT CHANGES LIMIT 5;
-- SELECT * FROM weather_stream EMIT CHANGES LIMIT 3;
-- SELECT * FROM users_table LIMIT 10;
