# Advanced Notes & Tips

## 🎯 Architecture Details

### Data Flow
```
NWS API → Python Producer → Kafka Topic (weather-data)
Sensors → Python Producer → Kafka Topic (iot-sensors)
PostgreSQL → JDBC Connector → Kafka Topic (postgres-users)
                                    ↓
                            ksqlDB Processing
                                    ↓
                    Enriched Streams & Dashboards
```

### City Matching Strategy
All three data sources use the **exact same city names**:
- New York
- Los Angeles
- Chicago
- San Francisco
- Miami

This enables clean joins in ksqlDB without transformation.

## 🔧 Customization

### Adding New Cities

**1. Add to NWS Weather Producer** (`producers/nws_weather_producer.py`):
```python
CITIES = [
    {'name': 'Seattle', 'state': 'WA', 'lat': 47.6062, 'lon': -122.3321},
    # ... existing cities
]
```

**2. Add to IoT Sensor Simulator** (`producers/iot_sensor_simulator.py`):
```python
SENSORS = [
    {
        'sensor_id': 'SENSOR_SEA_001',
        'location': 'Seattle',
        'state': 'WA',
        'latitude': 47.6062,
        'longitude': -122.3321,
        'base_temp': 52,
        'base_humidity': 75,
        'base_pressure': 1013,
        'base_aqi': 35
    },
    # ... existing sensors
]
```

**3. Add Users to Database** (`data/users.sql`):
```sql
INSERT INTO users (username, email, city, state, latitude, longitude) VALUES
('new_user', 'user@example.com', 'Seattle', 'WA', 47.6062, -122.3321);
```

### Adjusting Update Frequencies

**Weather Producer:**
```python
time.sleep(60)  # Change to 300 for 5 minutes
```

**IoT Sensors:**
```python
time.sleep(5)  # Change to 10 for 10 seconds
```

**JDBC Connector:**
```json
"poll.interval.ms": "5000"  // Change to 10000 for 10 seconds
```

## 📊 ksqlDB Advanced Patterns

### Windowed Aggregations

```sql
-- 5-minute tumbling window
SELECT
    location,
    WINDOWSTART as window_start,
    WINDOWEND as window_end,
    COUNT(*) as reading_count,
    AVG(temperature_fahrenheit) as avg_temp,
    MAX(air_quality_index) as max_aqi
FROM iot_sensors_stream
WINDOW TUMBLING (SIZE 5 MINUTES)
GROUP BY location
EMIT CHANGES;
```

### Hopping Windows

```sql
-- 10-minute window, advance every 5 minutes
SELECT
    city,
    WINDOWSTART,
    AVG(temperature_f) as avg_forecast_temp
FROM weather_stream
WINDOW HOPPING (SIZE 10 MINUTES, ADVANCE BY 5 MINUTES)
GROUP BY city
EMIT CHANGES;
```

### Session Windows

```sql
-- Group sensor readings with 30-second inactivity gap
SELECT
    sensor_id,
    WINDOWSTART,
    WINDOWEND,
    COUNT(*) as readings_in_session
FROM iot_sensors_stream
WINDOW SESSION (30 SECONDS)
GROUP BY sensor_id
EMIT CHANGES;
```

## 🔍 Monitoring & Debugging

### Check Kafka Consumer Groups

```bash
docker exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --list

docker exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --group connect-cluster
```

### View Connector Tasks

```bash
curl http://localhost:8083/connectors/postgres-users-source/tasks
```

### Monitor ksqlDB Queries

```sql
-- List all queries
SHOW QUERIES;

-- Describe a specific query
DESCRIBE EXTENDED user_local_sensors;

-- Terminate a query
TERMINATE query_id;
```

### View Topic Offsets

```bash
docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic weather-data
```

## 🚀 Performance Tuning

### Producer Optimization

```python
conf = {
    'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
    'client.id': 'producer-id',
    'batch.size': 16384,              # Increase batch size
    'linger.ms': 10,                  # Wait 10ms to batch
    'compression.type': 'snappy',     # Enable compression
    'acks': 1                         # Trade durability for speed
}
```

### Kafka Connect Performance

```json
{
  "tasks.max": "3",                    // Parallel tasks
  "batch.max.rows": "1000",           // Batch size
  "poll.interval.ms": "1000"          // Poll frequency
}
```

### ksqlDB Performance

```sql
-- Increase processing threads
SET 'ksql.streams.num.stream.threads' = '4';

-- Increase cache size
SET 'ksql.streams.cache.max.bytes.buffering' = '10485760';
```

## 🔒 Security Considerations

### Production Deployment Checklist

- [ ] Enable SASL/SSL for Kafka
- [ ] Use Schema Registry with authentication
- [ ] Encrypt database passwords in connectors
- [ ] Implement API rate limiting for weather API
- [ ] Use Kafka ACLs for topic access control
- [ ] Enable ksqlDB authentication
- [ ] Monitor and alert on connector failures
- [ ] Implement backup and disaster recovery

### Example SASL Configuration

```yaml
environment:
  KAFKA_SASL_ENABLED_MECHANISMS: PLAIN
  KAFKA_SASL_MECHANISM_INTER_BROKER_PROTOCOL: PLAIN
  KAFKA_SECURITY_INTER_BROKER_PROTOCOL: SASL_SSL
```

## 📈 Scaling Considerations

### Horizontal Scaling

**Kafka Brokers:**
```yaml
kafka-1:
  # ... config
kafka-2:
  # ... config
kafka-3:
  # ... config
```

**Kafka Connect Workers:**
```yaml
kafka-connect-1:
  environment:
    CONNECT_GROUP_ID: connect-cluster
kafka-connect-2:
  environment:
    CONNECT_GROUP_ID: connect-cluster
```

### Topic Partitioning

```bash
# Create topic with multiple partitions
docker exec kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --create \
  --topic weather-data \
  --partitions 3 \
  --replication-factor 1
```

## 🐛 Common Issues & Solutions

### Issue: Connector Fails to Start

**Solution:**
```bash
# Check Kafka Connect logs
docker logs kafka-connect

# Verify PostgreSQL is accessible
docker exec kafka-connect nc -zv postgres 5432

# Restart connector
curl -X POST http://localhost:8083/connectors/postgres-users-source/restart
```

### Issue: ksqlDB Query Not Processing Data

**Solution:**
```sql
-- Check stream is created
SHOW STREAMS;

-- Verify data in topic
PRINT 'weather-data' FROM BEGINNING LIMIT 5;

-- Check for errors
DESCRIBE EXTENDED weather_stream;
```

### Issue: Python Producer Not Connecting

**Solution:**
```bash
# Test Kafka connectivity
telnet localhost 9092

# Check producer logs
python3 producers/nws_weather_producer.py 2>&1 | tee debug.log

# Verify topic exists
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list
```

## 📚 Additional Resources

- [NWS API Documentation](https://www.weather.gov/documentation/services-web-api)
- [ksqlDB Reference](https://docs.ksqldb.io/)
- [Kafka Connect Guide](https://docs.confluent.io/platform/current/connect/)
- [Confluent Kafka Python](https://docs.confluent.io/kafka-clients/python/)

## 🎓 Learning Exercises

1. **Add Windowed Aggregations**: Calculate hourly averages
2. **Implement Change Data Capture**: Track user table changes
3. **Create Multiple Joins**: Combine 4+ streams
4. **Add Error Handling**: Dead letter queues for failed messages
5. **Build Visualization**: Connect to Grafana or custom dashboard
6. **Implement Exactly-Once**: Configure for zero data loss
7. **Add Schema Registry**: Use Avro serialization
8. **Create UDFs**: Custom ksqlDB functions in Java

## 💡 Best Practices

1. **Always use meaningful keys** for better partitioning
2. **Set appropriate retention** on topics
3. **Monitor consumer lag** in production
4. **Use Schema Registry** for production deployments
5. **Implement proper error handling** in producers
6. **Test with realistic data volumes** before production
7. **Document your stream processing logic**
8. **Use version control** for ksqlDB queries
