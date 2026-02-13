# QUICKSTART GUIDE - UPDATED
Complete step-by-step walkthrough for the Multi-Source Data Integration Tutorial

## ⚡ Prerequisites

- Docker & Docker Compose installed
- Python 3.8+ installed
- At least 4GB RAM available
- Internet connection (for NWS Weather API)

---

## 📦 Step 1: Start Infrastructure

```bash
# Navigate to tutorial directory
cd kafka-connect-tutorial

# Start all services
docker-compose -f docker/docker-compose.yml up -d
```

**Wait 2-3 minutes** for services to fully initialize.

### Verify Services

```bash
# Check all containers are running
docker-compose -f docker/docker-compose.yml ps

# All services should show "Up"
```

---

## 🗄️ Step 2: Initialize PostgreSQL Database

Load sample user data:

```bash
docker exec -i postgres psql -U envuser -d envdb < data/users.sql
```

### Verify Data

```bash
docker exec -it postgres psql -U envuser -d envdb -c \
  "SELECT city, state, COUNT(*) as users FROM users GROUP BY city, state ORDER BY city;"
```

**Expected:** 15 users across 5 cities (New York, Los Angeles, Chicago, San Francisco, Miami)

---

## 🐍 Step 3: Install Python Dependencies

```bash
pip3 install -r producers/requirements.txt
```

---

## 🌦️ Step 4: Start Data Producers

### Terminal 1: NWS Weather Producer

```bash
python3 producers/nws_weather_producer.py
```

**Expected output:**
```
============================================================
  NWS Weather.gov API Producer
============================================================
Kafka:  localhost:9092
Topic:  weather-data
...
  New York        |  45°F ( 7.2°C) | Partly Cloudy
✓ New York: weather-data [0] @ 0
```

**Keep this running!**

---

### Terminal 2: IoT Sensor Simulator

```bash
python3 producers/iot_sensor_simulator.py
```

**Expected output:**
```
============================================================
  IoT Environmental Sensor Simulator
============================================================
...
  New York        |  47.2°F | 68.5% | AQI:  48 (Good)
✓ SENSOR_NY_001: iot-sensors [0] @ 0
```

**Keep this running!**

---

### 💡 Or Run Both in Background

```bash
python3 producers/nws_weather_producer.py > weather.log 2>&1 &
python3 producers/iot_sensor_simulator.py > iot.log 2>&1 &

# View logs if needed
tail -f weather.log
tail -f iot.log
```

---

## 🔌 Step 5: Create JDBC Source Connector

**IMPORTANT:** Use **bulk mode** to ensure all existing users are loaded:

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
  "name": "postgres-users-source",
  "config": {
    "connector.class": "io.confluent.connect.jdbc.JdbcSourceConnector",
    "tasks.max": "1",
    "connection.url": "jdbc:postgresql://postgres:5432/envdb",
    "connection.user": "envuser",
    "connection.password": "envpass",
    "table.whitelist": "users",
    "mode": "bulk",
    "topic.prefix": "postgres-",
    "poll.interval.ms": "5000"
  }
}'
```

**Why bulk mode?** Incrementing mode only captures NEW users added after the connector starts. Bulk mode loads all existing users.

### Verify Connector

```bash
# Check status (wait 10 seconds first)
sleep 10
curl http://localhost:8083/connectors/postgres-users-source/status | jq

# Should show "state": "RUNNING"
```

---

## ✅ Step 6: Verify Kafka Topics & Data

### Check Topics Exist

```bash
docker exec kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --list
```

**You should see:**
- `weather-data`
- `iot-sensors`
- `postgres-users`

---

### Verify Data in Each Topic

**Weather data:**
```bash
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic weather-data \
  --from-beginning \
  --max-messages 2
```

**IoT sensor data:**
```bash
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic iot-sensors \
  --from-beginning \
  --max-messages 2
```

**User data (CRITICAL - verify this works!):**
```bash
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic postgres-users \
  --from-beginning \
  --max-messages 3
```

**Expected user output:**
```json
{"user_id":1,"username":"alice_smith","email":"alice@example.com","city":"New York",...}
```

**If you see nothing for postgres-users**, the connector isn't working. See troubleshooting below.

---

## 🎯 Step 7: Create ksqlDB Streams & Tables

Access ksqlDB CLI:

```bash
docker exec -it ksqldb-cli ksql http://ksqldb-server:8088
```

### Create All Streams

Copy/paste this entire block:

```sql
SET 'auto.offset.reset' = 'earliest';

-- Weather Stream
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

-- IoT Sensor Stream
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

-- Users Stream
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

-- Users Table (CITY as primary key for joins!)
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
```

---

### Verify Streams Created

```sql
SHOW STREAMS;
SHOW TABLES;
```

**Expected:**
```
Stream Name         | Kafka Topic
---------------------------------------
WEATHER_STREAM      | weather-data
IOT_SENSORS_STREAM  | iot-sensors
USERS_STREAM        | postgres-users

Table Name    | Kafka Topic
--------------------------------
USERS_TABLE   | users-table
```

---

### Test Data Flow

```sql
-- View weather (Ctrl+C to stop)
SELECT city, temperature_f, short_forecast 
FROM weather_stream 
EMIT CHANGES 
LIMIT 5;

-- View sensors
SELECT location, temperature_fahrenheit, air_quality_index 
FROM iot_sensors_stream 
EMIT CHANGES 
LIMIT 5;

-- View users table (should show 5 cities)
SELECT * FROM users_table;
```

**IMPORTANT:** `users_table` should show **5 rows** (one per city). If empty, see troubleshooting.

---

## 🔍 Step 8: Run Analysis Queries

### Query 1: Join Users with Local Sensors

```sql
SELECT 
    u.username,
    u.email,
    u.city,
    s.temperature_fahrenheit,
    s.air_quality_index,
    s.air_quality_status
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
EMIT CHANGES
LIMIT 10;
```

**Expected output:**
```
+----------+-------------------+----------+-------------+------+----------+
|USERNAME  |EMAIL              |CITY      |TEMPERATURE_ |AIR_  |AIR_QUALI |
+-----------+------------------+----------+-------------+------+----------+
|alice_smi |alice@example.com  |New York  |47.2         |48    |Good      |
|diana_gar |diana@example.com  |Los Ange..|75.8         |92    |Moderate  |
```

---

### Query 2: Complete Environmental Dashboard

Combines all 3 data sources:

```sql
CREATE STREAM complete_dashboard WITH (
    KAFKA_TOPIC='complete-dashboard',
    VALUE_FORMAT='JSON'
) AS SELECT
    u.user_id,
    u.username,
    u.city,
    s.temperature_fahrenheit as sensor_temp,
    s.air_quality_index,
    w.temperature_f as forecast_temp,
    w.short_forecast
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
INNER JOIN weather_stream w WITHIN 1 HOUR ON w.city = u.city
EMIT CHANGES;

-- View results
SELECT * FROM complete_dashboard EMIT CHANGES LIMIT 10;
```

---

### Query 3: Environmental Alerts

```sql
SELECT
    u.username,
    u.email,
    u.city,
    s.air_quality_index,
    s.temperature_fahrenheit,
    CASE
        WHEN s.air_quality_index > 150 THEN 'UNHEALTHY AIR - Stay indoors'
        WHEN s.temperature_fahrenheit > 95 THEN 'EXTREME HEAT - Stay hydrated'
        WHEN s.temperature_fahrenheit < 32 THEN 'FREEZE WARNING'
        ELSE 'NORMAL CONDITIONS'
    END as alert_message
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
WHERE s.air_quality_index > 100 
   OR s.temperature_fahrenheit > 90 
   OR s.temperature_fahrenheit < 35
EMIT CHANGES;
```

More queries available in `ksqldb/02_queries.sql`!

---

## 🛠️ Troubleshooting

### Issue: `postgres-users` Topic is Empty

**Cause:** Incrementing mode only captures NEW users, not existing ones.

**Solution:** Use bulk mode:

```bash
curl -X DELETE http://localhost:8083/connectors/postgres-users-source

curl -X POST http://localhost:8083/connectors -H "Content-Type: application/json" -d '{
  "name": "postgres-users-source",
  "config": {
    "connector.class": "io.confluent.connect.jdbc.JdbcSourceConnector",
    "tasks.max": "1",
    "connection.url": "jdbc:postgresql://postgres:5432/envdb",
    "connection.user": "envuser",
    "connection.password": "envpass",
    "table.whitelist": "users",
    "mode": "bulk",
    "topic.prefix": "postgres-",
    "poll.interval.ms": "5000"
  }
}'

sleep 10

# Verify
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic postgres-users \
  --from-beginning \
  --max-messages 3
```

---

### Issue: Join Query Hangs with No Results

**Cause:** Producers aren't running.

**Solution:**

```bash
# Check if running
ps aux | grep python3

# Start them
python3 producers/nws_weather_producer.py &
python3 producers/iot_sensor_simulator.py &
```

---

### Issue: ksqlDB Stream-Table Join Error

**Error:** `stream-table joins require to join on the table's primary key`

**Cause:** Trying to join on non-primary-key field.

**Solution:** Our `users_table` uses `city` as primary key, so join on city:
```sql
FROM iot_sensors_stream s
INNER JOIN users_table u ON s.location = u.city
```

---

### Issue: Cannot Drop Stream (Table Depends on It)

**Solution:** Drop table first, then stream:

```sql
DROP TABLE users_table DELETE TOPIC;
DROP STREAM users_stream DELETE TOPIC;
-- Then recreate
```

---

### Issue: Connector Not Running

```bash
# Check logs
docker logs kafka-connect --tail 50

# Check status
curl http://localhost:8083/connectors/postgres-users-source/status

# Restart if needed
curl -X POST http://localhost:8083/connectors/postgres-users-source/restart
```

---

## 🧹 Cleanup

```bash
# Stop producers
pkill -f nws_weather_producer
pkill -f iot_sensor_simulator

# Stop and remove all containers & data
docker-compose -f docker/docker-compose.yml down -v
```

---

## 🎓 What You've Accomplished

✅ Set up complete streaming infrastructure (Kafka, Connect, ksqlDB, PostgreSQL)  
✅ Integrated 3 data sources with matching cities  
✅ Created real-time data pipelines with Python producers  
✅ Configured Kafka Connect JDBC Source (bulk mode)  
✅ Built ksqlDB streams and tables with proper primary keys  
✅ Performed stream-table joins on city  
✅ Created real-time environmental monitoring dashboard  

## 🚀 Next Steps

1. Explore more queries in `ksqldb/02_queries.sql`
2. Add new cities to all three data sources
3. Create windowed aggregations (5-minute averages)
4. Build a visualization dashboard (Grafana)
5. Export processed streams to external systems

**Congratulations!** 🎉 You've built a complete multi-source streaming data pipeline!
