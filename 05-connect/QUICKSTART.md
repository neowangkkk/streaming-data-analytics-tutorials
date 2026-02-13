# QUICKSTART GUIDE

Complete step-by-step instructions to run the ksqlDB multi-source integration tutorial.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.8+ installed
- At least 4GB RAM available
- Internet connection (for Weather API)

## Step 1: Start Infrastructure

```bash
# Navigate to the tutorial directory
cd ksqldb-multi-source-tutorial

# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Verify services are running
docker-compose -f docker/docker-compose.yml ps
```

**Wait 2-3 minutes** for all services to fully start.

Check Kafka Connect is ready:
```bash
curl http://localhost:8083/
```

You should see: `{"version":"7.6.0",...}`

## Step 2: Initialize PostgreSQL Database

Load sample user data into PostgreSQL:

```bash
docker exec -i postgres psql -U envuser -d envdb < data/users.sql
```

Verify users were created:
```bash
docker exec -it postgres psql -U envuser -d envdb -c "SELECT * FROM users;"
```

You should see 10 users from different cities.

## Step 3: Start IoT Sensor Simulator

Install Python dependencies:
```bash
pip3 install -r producers/requirements.txt
```

Start the simulator (in a separate terminal):
```bash
python3 producers/iot_sensor_simulator.py
```

You should see output like:
```
=== IoT Sensor Simulator ===
Kafka: localhost:9092
Topic: iot-sensors
Sensors: 5

Starting data generation...

✓ Produced to iot-sensors [0] @ offset 0
✓ Produced to iot-sensors [0] @ offset 1
...
```

**Keep this running** in the background.

## Step 4: Create Kafka Connect Connectors

### Weather API Connector

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/weather-source.json
```

Expected response: `{"name":"weather-api-source",...}`

### PostgreSQL Connector

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/postgres-source.json
```

Expected response: `{"name":"postgres-users-source",...}`

### Verify Connectors

```bash
# List all connectors
curl http://localhost:8083/connectors

# Check connector status
curl http://localhost:8083/connectors/weather-api-source/status
curl http://localhost:8083/connectors/postgres-users-source/status
```

Both should show `"state":"RUNNING"`.

## Step 5: Verify Kafka Topics

Check that data is flowing into Kafka topics:

```bash
# List all topics
docker exec kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --list
```

You should see:
- `iot-sensors`
- `weather-data`
- `postgres-users`

View sample messages:
```bash
# IoT sensor data
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic iot-sensors \
  --from-beginning \
  --max-messages 3

# Weather data
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic weather-data \
  --from-beginning \
  --max-messages 1

# User data
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic postgres-users \
  --from-beginning \
  --max-messages 5
```

## Step 6: Create ksqlDB Streams and Tables

Access the ksqlDB CLI:
```bash
docker exec -it ksqldb-cli ksql http://ksqldb-server:8088
```

You should see:
```
                  ===========================================
                  =       _              _ ____  ____       =
                  =      | | _____  __ _| |  _ \| __ )      =
                  =      | |/ / __|/ _` | | | | |  _ \      =
                  =      |   <\__ \ (_| | | |_| | |_) |     =
                  =      |_|\_\___/\__, |_|____/|____/      =
                  =                   |_|                   =
                  =        The Database purpose-built       =
                  =        for stream processing apps       =
                  ===========================================

ksql>
```

### Run Stream Definitions

Copy and paste the contents of `ksqldb/streams.sql` into the ksqlDB CLI, or run:

```sql
-- Set offset
SET 'auto.offset.reset' = 'earliest';

-- Create IoT sensor stream
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

-- Create cleaned sensor stream
CREATE STREAM iot_sensors_stream WITH (
    KAFKA_TOPIC='iot-sensors-cleaned',
    VALUE_FORMAT='JSON'
) AS SELECT
    sensor_id,
    location,
    temperature_celsius,
    humidity_percent,
    pressure_hpa,
    air_quality_index
FROM iot_sensors_raw
EMIT CHANGES;

-- Create weather stream  
CREATE STREAM weather_raw (
    latitude DOUBLE,
    longitude DOUBLE,
    current STRUCT<
        temperature_2m DOUBLE,
        relative_humidity_2m INT,
        wind_speed_10m DOUBLE,
        pressure_msl DOUBLE
    >
) WITH (
    KAFKA_TOPIC='weather-data',
    VALUE_FORMAT='JSON'
);

-- Create users stream
CREATE STREAM users_stream (
    user_id INT,
    username VARCHAR,
    email VARCHAR,
    city VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE
) WITH (
    KAFKA_TOPIC='postgres-users',
    VALUE_FORMAT='JSON'
);

-- Create users table for lookups
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
```

### Verify Data is Flowing

```sql
-- Check IoT sensors
SELECT * FROM iot_sensors_stream EMIT CHANGES LIMIT 5;

-- Check users
SELECT * FROM users_table;

-- Press Ctrl+C to stop streaming queries
```

## Step 7: Run Stateless Processing Queries

### Query 1: Filter High Temperature Sensors

```sql
SELECT 
    sensor_id,
    location,
    temperature_celsius,
    humidity_percent
FROM iot_sensors_stream
WHERE temperature_celsius > 20
EMIT CHANGES
LIMIT 10;
```

### Query 2: Join Users with Their City Sensors

```sql
CREATE STREAM user_local_sensors WITH (
    KAFKA_TOPIC='user-local-sensors',
    VALUE_FORMAT='JSON'
) AS SELECT
    u.user_id,
    u.username,
    u.city,
    s.sensor_id,
    s.temperature_celsius,
    s.humidity_percent,
    s.air_quality_index
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
EMIT CHANGES;

-- View results
SELECT * FROM user_local_sensors EMIT CHANGES LIMIT 10;
```

### Query 3: Environmental Quality Alerts

```sql
SELECT 
    sensor_id,
    location,
    temperature_celsius,
    air_quality_index,
    CASE
        WHEN temperature_celsius > 30 THEN 'HEAT ALERT'
        WHEN air_quality_index > 150 THEN 'AIR QUALITY ALERT'
        ELSE 'NORMAL'
    END as alert_status
FROM iot_sensors_stream
WHERE temperature_celsius > 30 OR air_quality_index > 100
EMIT CHANGES
LIMIT 5;
```

### Query 4: Transform Data (Celsius to Fahrenheit)

```sql
SELECT 
    sensor_id,
    location,
    temperature_celsius,
    (temperature_celsius * 9/5) + 32 as temperature_fahrenheit,
    humidity_percent
FROM iot_sensors_stream
EMIT CHANGES
LIMIT 5;
```

## Step 8: Complete Dashboard Query

Combine all three data sources:

```sql
CREATE STREAM user_dashboard WITH (
    KAFKA_TOPIC='user-dashboard',
    VALUE_FORMAT='JSON'
) AS SELECT
    u.user_id,
    u.username,
    u.email,
    u.city,
    s.sensor_id,
    s.temperature_celsius,
    s.humidity_percent,
    s.air_quality_index,
    CASE 
        WHEN s.air_quality_index < 50 THEN 'Good'
        WHEN s.air_quality_index < 100 THEN 'Moderate'
        ELSE 'Unhealthy'
    END as air_quality_status
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
EMIT CHANGES;

-- View dashboard
SELECT * FROM user_dashboard EMIT CHANGES;
```

You should see output like:
```
+--------+------------+-------------------+----------+-----------+---------------+-------------+-------------+------------------+
|USER_ID |USERNAME    |EMAIL              |CITY      |SENSOR_ID  |TEMPERATURE_   |HUMIDITY_    |AIR_QUALITY_ |AIR_QUALITY_      |
|        |            |                   |          |           |CELSIUS        |PERCENT      |INDEX        |STATUS            |
+--------+------------+-------------------+----------+-----------+---------------+-------------+-------------+------------------+
|1       |alice_smith |alice@example.com  |Toronto   |SENSOR_001 |18.45          |62.3         |45           |Good              |
|6       |fiona_chen  |fiona@example.com  |Toronto   |SENSOR_001 |18.45          |62.3         |45           |Good              |
...
```

## Troubleshooting

### Connectors not starting

```bash
# View connector logs
docker logs kafka-connect

# Restart a connector
curl -X POST http://localhost:8083/connectors/weather-api-source/restart
```

### No data in topics

```bash
# Check if simulator is still running
ps aux | grep iot_sensor

# Restart it if needed
python3 producers/iot_sensor_simulator.py &
```

### ksqlDB errors

```bash
# Restart ksqlDB server
docker restart ksqldb-server

# Wait 30 seconds, then reconnect
docker exec -it ksqldb-cli ksql http://ksqldb-server:8088
```

## Cleanup

```bash
# Stop simulator
pkill -f iot_sensor_simulator

# Stop all services
docker-compose -f docker/docker-compose.yml down -v

# This removes all data and volumes
```

## Next Steps

1. Explore more queries in `ksqldb/queries.sql`
2. Add new sensors with different locations
3. Create aggregation queries with windows
4. Export processed streams to external systems

## Summary

You've successfully:
✅ Connected to a REST API (Weather)
✅ Created a custom Python producer (IoT sensors)
✅ Imported database data via JDBC (PostgreSQL)
✅ Created ksqlDB streams and tables
✅ Performed stateless transformations and joins
✅ Built a real-time environmental monitoring dashboard!
