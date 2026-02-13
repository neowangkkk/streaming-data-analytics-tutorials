-- ========================================
-- ksqlDB Analysis Queries
-- Multi-Source Data Integration Examples
-- ========================================

-- ========================================
-- QUERY 1: Hot Weather Alerts
-- Filter cities with high temperatures
-- ========================================
SELECT 
    city,
    state,
    temperature_f,
    temperature_c,
    short_forecast,
    CASE
        WHEN temperature_f > 90 THEN 'EXTREME HEAT ALERT'
        WHEN temperature_f > 80 THEN 'HOT'
        ELSE 'NORMAL'
    END as heat_alert
FROM weather_stream
WHERE temperature_f > 80
EMIT CHANGES;

-- ========================================
-- QUERY 2: Poor Air Quality Sensors
-- Find locations with unhealthy air
-- ========================================
SELECT 
    location,
    state,
    air_quality_index,
    air_quality_status,
    temperature_fahrenheit,
    humidity_percent
FROM iot_sensors_stream
WHERE air_quality_index > 100
EMIT CHANGES;

-- ========================================
-- QUERY 3: Join Users with Local Sensors
-- Stream-Table Join Pattern
-- ========================================
CREATE STREAM user_local_sensors WITH (
    KAFKA_TOPIC='user-local-sensors',
    VALUE_FORMAT='JSON',
    PARTITIONS=1
) AS SELECT
    u.user_id,
    u.username,
    u.email,
    u.city,
    u.state,
    s.sensor_id,
    s.temperature_fahrenheit as sensor_temp_f,
    s.humidity_percent,
    s.air_quality_index,
    s.air_quality_status,
    s.timestamp as reading_time
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
EMIT CHANGES;

-- View results
-- SELECT * FROM user_local_sensors EMIT CHANGES LIMIT 10;

-- ========================================
-- QUERY 4: Join Users with Weather Forecasts
-- Personalized Weather Dashboard
-- ========================================
CREATE STREAM user_weather_dashboard WITH (
    KAFKA_TOPIC='user-weather-dashboard',
    VALUE_FORMAT='JSON',
    PARTITIONS=1
) AS SELECT
    u.user_id,
    u.username,
    u.email,
    u.city,
    u.state,
    w.temperature_f,
    w.temperature_c,
    w.wind_speed,
    w.wind_direction,
    w.short_forecast,
    w.period_name,
    w.timestamp as forecast_time
FROM weather_stream w
INNER JOIN users_table u ON w.city = u.city
EMIT CHANGES;

-- View results
-- SELECT * FROM user_weather_dashboard EMIT CHANGES LIMIT 10;

-- ========================================
-- QUERY 5: Complete Environmental Dashboard
-- Combines ALL THREE data sources!
-- ========================================
CREATE STREAM complete_dashboard WITH (
    KAFKA_TOPIC='complete-dashboard',
    VALUE_FORMAT='JSON',
    PARTITIONS=1
) AS SELECT
    u.user_id,
    u.username,
    u.email,
    u.city,
    u.state,
    -- Sensor data
    s.sensor_id,
    s.temperature_fahrenheit as sensor_temp,
    s.humidity_percent,
    s.pressure_hpa,
    s.air_quality_index,
    s.air_quality_status,
    -- Weather forecast data  
    w.temperature_f as forecast_temp,
    w.short_forecast,
    w.wind_speed,
    -- Combined insights
    CASE 
        WHEN s.air_quality_index > 150 THEN 'AIR QUALITY WARNING'
        WHEN s.temperature_fahrenheit > 95 THEN 'HEAT WARNING'
        WHEN s.temperature_fahrenheit < 32 THEN 'FREEZE WARNING'
        ELSE 'NORMAL'
    END as alert_status
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
INNER JOIN weather_stream w WITHIN 1 HOUR ON w.city = u.city
EMIT CHANGES;

-- View complete dashboard
-- SELECT * FROM complete_dashboard EMIT CHANGES;

-- ========================================
-- QUERY 6: Temperature Comparison
-- Sensor vs Forecast
-- ========================================
SELECT
    w.city,
    w.temperature_f as nws_forecast_temp,
    s.temperature_fahrenheit as sensor_actual_temp,
    ABS(w.temperature_f - s.temperature_fahrenheit) as temp_difference,
    CASE 
        WHEN ABS(w.temperature_f - s.temperature_fahrenheit) > 10 THEN 'LARGE VARIANCE'
        WHEN ABS(w.temperature_f - s.temperature_fahrenheit) > 5 THEN 'MODERATE VARIANCE'
        ELSE 'CLOSE MATCH'
    END as variance_status
FROM weather_stream w
INNER JOIN iot_sensors_stream s WITHIN 1 MINUTE ON w.city = s.location
EMIT CHANGES;

-- ========================================
-- QUERY 7: City Environmental Summary
-- Aggregate by city
-- ========================================
SELECT
    location as city,
    COUNT(*) as reading_count,
    ROUND(AVG(temperature_fahrenheit), 1) as avg_temp_f,
    ROUND(AVG(humidity_percent), 1) as avg_humidity,
    ROUND(AVG(air_quality_index), 0) as avg_aqi,
    MAX(air_quality_index) as max_aqi
FROM iot_sensors_stream
WINDOW TUMBLING (SIZE 1 MINUTE)
GROUP BY location
EMIT CHANGES;

-- ========================================
-- QUERY 8: User Alert Stream
-- Notify users of environmental alerts
-- ========================================
CREATE STREAM user_alerts WITH (
    KAFKA_TOPIC='user-alerts',
    VALUE_FORMAT='JSON',
    PARTITIONS=1
) AS SELECT
    u.username,
    u.email,
    u.city,
    s.air_quality_index,
    s.temperature_fahrenheit,
    CASE
        WHEN s.air_quality_index > 150 THEN 'UNHEALTHY AIR QUALITY - Stay indoors if possible'
        WHEN s.temperature_fahrenheit > 95 THEN 'EXTREME HEAT - Stay hydrated'
        WHEN s.temperature_fahrenheit < 32 THEN 'FREEZING TEMPERATURES - Protect pipes'
        WHEN s.humidity_percent > 90 THEN 'VERY HIGH HUMIDITY - Mold risk'
        ELSE 'NORMAL CONDITIONS'
    END as alert_message,
    s.timestamp as alert_time
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
WHERE s.air_quality_index > 150 
   OR s.temperature_fahrenheit > 95 
   OR s.temperature_fahrenheit < 32
   OR s.humidity_percent > 90
EMIT CHANGES;

-- View alerts
-- SELECT * FROM user_alerts EMIT CHANGES;

-- ========================================
-- QUERY 9: Temperature Unit Conversion
-- Show both Fahrenheit and Celsius
-- ========================================
SELECT
    sensor_id,
    location,
    temperature_fahrenheit,
    temperature_celsius,
    ROUND((temperature_fahrenheit - 32) * 5 / 9, 2) as calculated_celsius,
    humidity_percent,
    air_quality_status
FROM iot_sensors_stream
EMIT CHANGES
LIMIT 10;

-- ========================================
-- QUERY 10: Count Users by City
-- ========================================
SELECT
    city,
    state,
    COUNT(*) as user_count
FROM users_table
GROUP BY city, state
EMIT CHANGES;
