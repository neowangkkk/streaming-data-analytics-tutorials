# Tutorial: Multi-Source Data Integration with Kafka Connect & ksqlDB

A complete, hands-on tutorial demonstrating real-time data integration from multiple sources using Kafka, ksqlDB, and different integration patterns.

## What You'll Build

A real-time environmental monitoring system that combines:
1. **NWS Weather API** - Official US weather data via Python producer (HTTP/REST integration)
2. **IoT Sensors** - Simulated environmental sensors via Python producer
3. **PostgreSQL** - User location preferences via JDBC Source Connector

All sources use **matching US cities** for seamless joining in ksqlDB!

## Architecture

```
┌──────────────────┐
│  weather.gov API │ (Official NWS)
│  HTTP/REST       │
└────────┬─────────┘
         │
         ▼
    ┌─────────────────┐
    │ Python Producers │
    └────────┬─────────┘
         │
         ▼                    ┌──────────────┐
┌──────────────┐              │   ksqlDB     │
│  PostgreSQL  │─────────────▶│   Server     │
│ (JDBC Conn.) │   Kafka      └──────┬───────┘
└──────────────┘   Topics            │
                                     ▼
                              ┌──────────────┐
                              │  Processed   │
                              │   Streams    │
                              └──────────────┘
```

## Cities Used (All Sources)

- **New York, NY**
- **Los Angeles, CA**
- **Chicago, IL**
- **San Francisco, CA**
- **Miami, FL**

These cities are consistent across weather API, IoT sensors, and user database for easy joining!

## Quick Start

```bash
# 1. Start services
docker-compose -f docker/docker-compose.yml up -d

# 2. Wait for startup (2 minutes)
sleep 120

# 3. Initialize database
docker exec -i postgres psql -U envuser -d envdb < data/users.sql

# 4. Install Python dependencies
pip3 install -r producers/requirements.txt

# 5. Start producers
python3 producers/nws_weather_producer.py &
python3 producers/iot_sensor_simulator.py &

# 6. Create PostgreSQL connector
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/postgres-source.json

# 7. Access ksqlDB
docker exec -it ksqldb-cli ksql http://ksqldb-server:8088
```

## Project Structure

```
kafka-connect-tutorial/
├── README.md                    # This file
├── QUICKSTART.md                # Step-by-step guide
├── docker/
│   └── docker-compose.yml       # All services
├── connectors/
│   └── postgres-source.json     # JDBC connector
├── producers/
│   ├── nws_weather_producer.py  # NWS weather data
│   ├── iot_sensor_simulator.py  # IoT sensor data
│   └── requirements.txt         # Python deps
├── ksqldb/
│   ├── 01_create_streams.sql    # Stream definitions
│   └── 02_queries.sql           # Analysis queries
├── data/
│   └── users.sql                # Sample users (5 cities)
└── scripts/
    └── setup.sh                 # Automated setup
```

## What You'll Learn

- **HTTP/REST API Integration** - Fetching from NWS weather API
- **Kafka Connect JDBC** - Database integration with zero code
- **Python Kafka Producers** - Building custom data pipelines
- **ksqlDB Stream Processing** - Real-time data transformation
- **Stream-Table Joins** - Combining multiple data sources
- **Stateless Processing** - Filtering, mapping, enriching

## 💡 Use Case: Smart City Environmental Dashboard

**Goal**: Provide residents with real-time environmental data for their city

**Data Flow**:
1. Official weather forecasts from NWS (temperature, conditions, wind)
2. Local IoT sensors report air quality, humidity, pressure
3. User profiles contain city preferences
4. ksqlDB joins all sources by city name
5. Real-time personalized environmental dashboard

## Requirements

- Docker & Docker Compose
- Python 3.8+
- 4GB RAM minimum
- Internet connection (for NWS API)

## Data Sources

### 1. NWS Weather API (weather.gov)
- **Type**: Python Producer (HTTP)
- **API**: https://api.weather.gov (Official US Government)
- **Features**: Free, no authentication, detailed forecasts
- **Update**: Every 60 seconds

### 2. IoT Sensor Simulator
- **Type**: Python Producer
- **Data**: Temperature, humidity, pressure, air quality
- **Update**: Every 5 seconds
- **Devices**: 5 sensors (one per city)

### 3. PostgreSQL User Database
- **Type**: JDBC Source Connector
- **Data**: User profiles with city preferences
- **Mode**: Incremental (tracks new users)
- **Users**: 15 sample users across 5 cities

## 🎯 Key Features

✅ **All cities match** across all three data sources
✅ **Real US weather data** from official NWS API
✅ **Production-ready patterns** (error handling, callbacks)
✅ **Complete documentation** with troubleshooting
✅ **Automated setup** script included

## 📚 Next Steps

1. Complete [QUICKSTART.md](QUICKSTART.md)
2. Experiment with ksqlDB queries
3. Add new cities or data sources
4. Build aggregation queries
5. Create a visualization dashboard

## 📝 License

MIT License - Free for educational use
