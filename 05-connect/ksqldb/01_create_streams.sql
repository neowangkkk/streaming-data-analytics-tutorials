-- ========================================
-- ksqlDB Stream and Table Definitions
-- ========================================

SET 'auto.offset.reset' = 'earliest';

-- ========================================
-- 1. WEATHER DATA STREAM (NWS API)
-- ========================================
CREATE STREAM weather_stream (
    city VARCHAR,
    state VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    timestamp VARCHAR,
    temperature_f INT,
    temperature_c DOUBLE,
    temperature_unit VARCHAR,
    wind_speed VARCHAR,
    wind_direction VARCHAR,
    short_forecast VARCHAR,
    detailed_forecast VARCHAR,
    is_daytime BOOLEAN,
    period_name VARCHAR,
    icon VARCHAR
) WITH (
    KAFKA_TOPIC='weather-data',
    VALUE_FORMAT='JSON'
);

-- ========================================
-- 2. IOT SENSOR STREAM
-- ========================================
CREATE STREAM iot_sensors_stream (
    sensor_id VARCHAR,
    location VARCHAR,
    state VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    timestamp VARCHAR,
    temperature_celsius DOUBLE,
    temperature_fahrenheit DOUBLE,
    humidity_percent DOUBLE,
    pressure_hpa DOUBLE,
    air_quality_index INT,
    air_quality_status VARCHAR
) WITH (
    KAFKA_TOPIC='iot-sensors',
    VALUE_FORMAT='JSON'
);

-- ========================================
-- 3. USERS STREAM (from PostgreSQL)
-- ========================================
CREATE STREAM users_stream (
    user_id INT,
    username VARCHAR,
    email VARCHAR,
    city VARCHAR,
    state VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    created_at BIGINT
) WITH (
    KAFKA_TOPIC='postgres-users',
    VALUE_FORMAT='JSON'
);

-- ========================================
-- 4. USERS TABLE (for lookups)
-- IMPORTANT: city is PRIMARY KEY for joins!
-- ========================================
CREATE TABLE users_table 
WITH (
    KAFKA_TOPIC='users-table',
    VALUE_FORMAT='JSON'
) AS SELECT
    city,
    LATEST_BY_OFFSET(user_id) as user_id,
    LATEST_BY_OFFSET(username) as username,
    LATEST_BY_OFFSET(email) as email,
    LATEST_BY_OFFSET(state) as state,
    LATEST_BY_OFFSET(latitude) as latitude,
    LATEST_BY_OFFSET(longitude) as longitude
FROM users_stream
GROUP BY city
EMIT CHANGES;

-- ========================================
-- VERIFY DATA IS FLOWING
-- ========================================
-- View weather data (Ctrl+C to stop)
-- SELECT city, temperature_f, short_forecast FROM weather_stream EMIT CHANGES LIMIT 5;

-- View IoT sensors
-- SELECT location, temperature_fahrenheit, air_quality_index FROM iot_sensors_stream EMIT CHANGES LIMIT 5;

-- View users (should show 5 rows - one per city)
-- SELECT * FROM users_table;
