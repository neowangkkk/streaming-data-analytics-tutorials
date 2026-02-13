# Tutorial Notes & Tips

## Architecture Overview

This tutorial demonstrates a complete streaming data pipeline with three distinct data sources:

### Data Sources

1. **Open-Meteo Weather API** (HTTP Source Connector)
   - Real-time weather data
   - Polls API every 60 seconds
   - No authentication required
   - Data includes: temperature, humidity, wind speed, pressure

2. **IoT Sensor Simulator** (Python Producer)
   - Simulates 5 sensors in different cities
   - Generates readings every 5 seconds
   - Matches cities with user data for easy joins
   - Data includes: temperature, humidity, pressure, air quality

3. **PostgreSQL Database** (JDBC Source Connector)
   - User profiles with location preferences
   - Incrementing mode (tracks new users)
   - 10 sample users across multiple cities
   - Data includes: user_id, username, email, city, coordinates

### Data Flow

```
External Sources → Kafka Connect → Kafka Topics → ksqlDB → Processed Streams
```

## Key Concepts Demonstrated

### 1. Connector Configuration

**HTTP Connector** - For REST APIs
- Automatic polling at intervals
- JSON response parsing
- No code required

**JDBC Connector** - For databases
- Incremental mode using auto-increment column
- Automatic schema detection
- Change data capture capability

**Python Producer** - For custom sources
- Full control over data format
- Custom business logic
- Real-time generation

### 2. ksqlDB Stream Processing

**Streams** - Unbounded, append-only sequences
- `iot_sensors_stream` - Continuous sensor readings
- `weather_stream` - Periodic weather updates

**Tables** - Mutable, current state
- `users_table` - Latest user information
- Key-value lookups

**Joins** - Combining data sources
- Stream-Table join: sensors with users
- Enrichment pattern

## Common Patterns

### Data Cleansing
```sql
CREATE STREAM cleaned AS SELECT
    TRIM(field1) as field1,
    CAST(field2 AS DOUBLE) as field2
FROM raw_stream;
```

### Filtering
```sql
SELECT * FROM stream
WHERE condition = true
EMIT CHANGES;
```

### Transformation
```sql
SELECT 
    field1,
    field2 * 1.5 as calculated_field,
    CASE WHEN field3 > 10 THEN 'HIGH' ELSE 'LOW' END as category
FROM stream;
```

### Enrichment (Join)
```sql
SELECT s.*, t.additional_info
FROM stream s
INNER JOIN table t ON s.key = t.key;
```

## Stateless vs Stateful Processing

### Stateless (This Tutorial)
- **No aggregation** - Process each event independently
- **Operations**: filter, map, select, join
- **Memory**: Minimal (no state storage)
- **Examples**: 
  - Filter hot sensors
  - Convert temperature units
  - Enrich with user info

### Stateful (Advanced, not covered)
- **Aggregation** - Group and summarize events
- **Operations**: GROUP BY, windows, COUNT, AVG, SUM
- **Memory**: Stores intermediate state
- **Examples**:
  - Average temperature per hour
  - Count events per location
  - Session windows

## Troubleshooting Guide

### Issue: Connector won't start

**Symptoms**: Status shows "FAILED"

**Solution**:
```bash
# Check logs
docker logs kafka-connect

# Common issues:
# 1. Wrong credentials
# 2. Network connectivity
# 3. Invalid JSON config

# Fix config and restart
curl -X POST http://localhost:8083/connectors/NAME/restart
```

### Issue: No data in ksqlDB

**Symptoms**: SELECT returns empty

**Solutions**:
```sql
-- Check if topic exists
SHOW TOPICS;

-- Check if data in topic
PRINT 'topic-name' FROM BEGINNING;

-- Verify offset setting
SET 'auto.offset.reset' = 'earliest';
```

### Issue: Join returns no results

**Common causes**:
1. Keys don't match (case sensitive!)
2. Table hasn't been populated yet
3. Wrong join type (try LEFT JOIN)

**Debug**:
```sql
-- Check both sides independently
SELECT * FROM stream EMIT CHANGES LIMIT 5;
SELECT * FROM table LIMIT 5;

-- Verify join key exists
SELECT key_field FROM stream EMIT CHANGES LIMIT 10;
```

### Issue: Python simulator crashes

**Check**:
```bash
# Verify Kafka is accessible
nc -zv localhost 9092

# Check Python dependencies
pip3 list | grep confluent-kafka

# Run with debugging
python3 producers/iot_sensor_simulator.py 2>&1 | tee simulator.log
```

## Performance Tips

### 1. Connector Tuning
```json
{
  "tasks.max": "3",           // Parallel tasks
  "poll.interval.ms": "5000", // Polling frequency
  "batch.size": "100"         // Records per batch
}
```

### 2. ksqlDB Optimization
```sql
-- Limit results for testing
SELECT * FROM stream EMIT CHANGES LIMIT 10;

-- Use specific columns
SELECT col1, col2 FROM stream;  -- Not SELECT *

-- Filter early
WHERE condition  -- Before joins when possible
```

### 3. Topic Configuration
```bash
# Increase partitions for parallelism
kafka-topics --alter --topic my-topic --partitions 3 --bootstrap-server localhost:9092

# Set retention
kafka-configs --alter --topic my-topic \
  --add-config retention.ms=86400000 \
  --bootstrap-server localhost:9092
```

## Extending the Tutorial

### Add More Data Sources

1. **Twitter API** - Social media mentions
2. **Stock Prices** - Financial data streams
3. **Traffic APIs** - Real-time traffic data
4. **MongoDB** - NoSQL database connector

### Advanced Processing

1. **Windowed Aggregations**
   ```sql
   SELECT location, AVG(temperature_celsius)
   FROM iot_sensors_stream
   WINDOW TUMBLING (SIZE 1 HOUR)
   GROUP BY location;
   ```

2. **Complex Joins**
   ```sql
   -- Three-way join
   SELECT u.*, s.*, w.*
   FROM users_table u
   JOIN iot_sensors_stream s ON u.city = s.location
   LEFT JOIN weather_stream w ON u.city = w.city;
   ```

3. **User-Defined Functions (UDFs)**
   - Write custom Java functions
   - Complex calculations
   - External API calls

## Real-World Use Cases

### IoT Monitoring
- Device health monitoring
- Predictive maintenance
- Real-time alerting

### E-commerce
- Inventory updates
- Order processing
- Fraud detection

### Finance
- Market data analysis
- Risk calculations
- Compliance monitoring

### Smart Cities
- Traffic management
- Environmental monitoring
- Energy optimization

## Additional Resources

- [ksqlDB Documentation](https://docs.ksqldb.io/)
- [Kafka Connect Guide](https://docs.confluent.io/platform/current/connect/)
- [Stream Processing Patterns](https://www.confluent.io/blog/streaming-design-patterns/)
- [Open-Meteo API](https://open-meteo.com/en/docs)

## Learning Path

1. ✅ Complete this tutorial
2. Modify queries to add new transformations
3. Add aggregation queries with windows
4. Create your own data source
5. Build a complete streaming application
6. Deploy to production (Docker Swarm/Kubernetes)
