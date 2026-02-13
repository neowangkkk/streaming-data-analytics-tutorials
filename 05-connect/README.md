# ksqlDB Multi-Source Integration Tutorial

A complete, hands-on tutorial demonstrating how to connect three different data sources to Kafka and process them with ksqlDB.

## 📋 What You'll Build

A real-time environmental monitoring system that combines:
1. **Weather API** - Real weather data from Open-Meteo API
2. **IoT Sensors** - Simulated sensor data (temperature, humidity, pressure)
3. **User Database** - PostgreSQL table with user location preferences

## 🎯 Architecture

```
┌──────────────────┐
│  Open-Meteo API  │──┐
│  (Weather Data)  │  │
└──────────────────┘  │
                      ▼
┌──────────────────┐  ┌─────────────┐     ┌──────────┐
│  IoT Simulator   │─▶│    Kafka    │────▶│  ksqlDB  │
│  (Python)        │  │   Topics    │     │  Server  │
└──────────────────┘  └─────────────┘     └──────────┘
                      ▲                         │
┌──────────────────┐  │                         │
│   PostgreSQL     │──┘                         ▼
│  (User Profiles) │                    ┌──────────────┐
└──────────────────┘                    │  Processed   │
                                        │   Streams    │
                                        └──────────────┘
```

## 🚀 Quick Start

```bash
# 1. Navigate to tutorial directory
cd ksqldb-multi-source-tutorial

# 2. Start all services
docker-compose -f docker/docker-compose.yml up -d

# 3. Wait for services (2-3 minutes), then initialize database
docker exec -i postgres psql -U envuser -d envdb < data/users.sql

# 4. Start IoT simulator in background
pip3 install -r producers/requirements.txt
python3 producers/iot_sensor_simulator.py &

# 5. Create connectors
curl -X POST http://localhost:8083/connectors -H "Content-Type: application/json" -d @connectors/weather-source.json
curl -X POST http://localhost:8083/connectors -H "Content-Type: application/json" -d @connectors/postgres-source.json

# 6. Access ksqlDB and run queries
docker exec -it ksqldb-cli ksql http://ksqldb-server:8088
```

## 📊 What You'll Learn

- HTTP Source Connector for REST APIs
- JDBC Source Connector for databases
- Python Kafka producers
- ksqlDB stream creation
- Stateless transformations and joins

## 💡 Use Case

Match users with environmental data from their location in real-time.

## 📦 Requirements

- Docker & Docker Compose
- Python 3.8+
- 4GB RAM minimum

See **QUICKSTART.md** for detailed step-by-step instructions.
