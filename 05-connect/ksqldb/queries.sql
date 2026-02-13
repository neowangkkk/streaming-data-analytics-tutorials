-- ============================================================================
-- Stateless Stream Processing Examples
-- ============================================================================

SET 'auto.offset.reset' = 'earliest';

-- ============================================================================
-- QUERY 1: Filter High Temperature Sensors
-- ============================================================================
-- Find sensors reporting temperatures above 25°C

CREATE STREAM hot_sensors WITH (
    KAFKA_TOPIC='hot-sensors',
    VALUE_FORMAT='JSON'
) AS SELECT
    sensor_id,
    location,
    temperature_celsius,
    humidity_percent,
    air_quality_index,
    event_time
FROM iot_sensors_stream
WHERE temperature_celsius > 25
EMIT CHANGES;

-- Test query:
-- SELECT * FROM hot_sensors EMIT CHANGES;

-- ============================================================================
-- QUERY 2: Enrich Sensor Data with Location Info
-- ============================================================================
-- Add city name and clean up the output

CREATE STREAM sensors_enriched WITH (
    KAFKA_TOPIC='sensors-enriched',
    VALUE_FORMAT='JSON'
) AS SELECT
    sensor_id,
    location as city,
    CONCAT('Sensor ', sensor_id, ' in ', location) as sensor_description,
    temperature_celsius,
    humidity_percent,
    pressure_hpa,
    CASE 
        WHEN air_quality_index < 50 THEN 'Good'
        WHEN air_quality_index < 100 THEN 'Moderate'
        WHEN air_quality_index < 150 THEN 'Unhealthy for Sensitive'
        ELSE 'Unhealthy'
    END as air_quality_status,
    event_time
FROM iot_sensors_stream
EMIT CHANGES;

-- Test query:
-- SELECT * FROM sensors_enriched EMIT CHANGES LIMIT 10;

-- ============================================================================
-- QUERY 3: Match Users with Their City Sensors
-- ============================================================================
-- Join users with sensors in their city

CREATE STREAM user_local_sensors WITH (
    KAFKA_TOPIC='user-local-sensors',
    VALUE_FORMAT='JSON'
) AS SELECT
    u.user_id,
    u.username,
    u.email,
    u.city,
    s.sensor_id,
    s.temperature_celsius,
    s.humidity_percent,
    s.pressure_hpa,
    s.air_quality_index,
    s.event_time
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
EMIT CHANGES;

-- Test query:
-- SELECT * FROM user_local_sensors EMIT CHANGES;

-- ============================================================================
-- QUERY 4: Environmental Alerts
-- ============================================================================
-- Alert when conditions are concerning

CREATE STREAM environmental_alerts WITH (
    KAFKA_TOPIC='environmental-alerts',
    VALUE_FORMAT='JSON'
) AS SELECT
    sensor_id,
    location,
    temperature_celsius,
    humidity_percent,
    air_quality_index,
    CASE
        WHEN temperature_celsius > 30 THEN 'HEAT ALERT'
        WHEN temperature_celsius < 0 THEN 'FREEZE ALERT'
        WHEN air_quality_index > 150 THEN 'AIR QUALITY ALERT'
        WHEN humidity_percent > 85 THEN 'HIGH HUMIDITY ALERT'
        ELSE 'NORMAL'
    END as alert_type,
    event_time
FROM iot_sensors_stream
WHERE temperature_celsius > 30 
   OR temperature_celsius < 0 
   OR air_quality_index > 150 
   OR humidity_percent > 85
EMIT CHANGES;

-- Test query:
-- SELECT * FROM environmental_alerts EMIT CHANGES;

-- ============================================================================
-- QUERY 5: User Dashboard - Complete Picture
-- ============================================================================
-- Combine all three data sources for a user dashboard

CREATE STREAM user_environmental_dashboard WITH (
    KAFKA_TOPIC='user-dashboard',
    VALUE_FORMAT='JSON'
) AS SELECT
    u.user_id,
    u.username,
    u.email,
    u.city as user_city,
    s.sensor_id,
    s.temperature_celsius as sensor_temp,
    s.humidity_percent as sensor_humidity,
    s.pressure_hpa as sensor_pressure,
    s.air_quality_index,
    CASE 
        WHEN s.air_quality_index < 50 THEN 'Good'
        WHEN s.air_quality_index < 100 THEN 'Moderate'
        WHEN s.air_quality_index < 150 THEN 'Unhealthy for Sensitive'
        ELSE 'Unhealthy'
    END as air_quality,
    s.event_time as reading_time
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
EMIT CHANGES;

-- Test query:
-- SELECT * FROM user_environmental_dashboard EMIT CHANGES;

-- To see results for a specific user:
-- SELECT * FROM user_environmental_dashboard 
-- WHERE username = 'alice_smith' 
-- EMIT CHANGES;

-- ============================================================================
-- QUERY 6: Simple Data Transformation
-- ============================================================================
-- Convert temperature to Fahrenheit and add derived fields

CREATE STREAM sensors_converted WITH (
    KAFKA_TOPIC='sensors-converted',
    VALUE_FORMAT='JSON'
) AS SELECT
    sensor_id,
    location,
    temperature_celsius,
    (temperature_celsius * 9/5) + 32 as temperature_fahrenheit,
    humidity_percent,
    pressure_hpa,
    -- Calculate heat index approximation
    CASE 
        WHEN temperature_celsius > 27 AND humidity_percent > 40 
        THEN temperature_celsius + ((humidity_percent / 100) * 5)
        ELSE temperature_celsius
    END as feels_like_celsius,
    air_quality_index,
    event_time
FROM iot_sensors_stream
EMIT CHANGES;

-- Test query:
-- SELECT 
--     sensor_id, 
--     temperature_celsius, 
--     temperature_fahrenheit, 
--     feels_like_celsius 
-- FROM sensors_converted 
-- EMIT CHANGES 
-- LIMIT 10;

-- ============================================================================
-- Ad-Hoc Queries (run these interactively)
-- ============================================================================

-- Count sensors by location
-- SELECT location, COUNT(*) as sensor_count 
-- FROM iot_sensors_stream 
-- WINDOW TUMBLING (SIZE 1 MINUTE)
-- GROUP BY location 
-- EMIT CHANGES;

-- Average temperature by location
-- SELECT 
--     location, 
--     AVG(temperature_celsius) as avg_temp,
--     AVG(humidity_percent) as avg_humidity
-- FROM iot_sensors_stream 
-- WINDOW TUMBLING (SIZE 1 MINUTE)
-- GROUP BY location 
-- EMIT CHANGES;

-- Find users in cities with poor air quality
-- SELECT DISTINCT u.username, u.city, s.air_quality_index
-- FROM iot_sensors_stream s
-- INNER JOIN users_table u ON s.location = u.city
-- WHERE s.air_quality_index > 100
-- EMIT CHANGES;
