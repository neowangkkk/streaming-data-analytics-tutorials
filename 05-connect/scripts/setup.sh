#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  Kafka Connect & ksqlDB Multi-Source Tutorial Setup${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"
command -v docker >/dev/null 2>&1 || { echo -e "${RED}✗ Docker not found. Please install Docker.${NC}"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo -e "${RED}✗ Docker Compose not found.${NC}"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}✗ Python 3 not found.${NC}"; exit 1; }
echo -e "${GREEN}✓ All prerequisites found${NC}"
echo ""

# Start Docker services
echo -e "${YELLOW}Step 2: Starting Docker services...${NC}"
docker-compose -f docker/docker-compose.yml up -d
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Services started${NC}"
else
    echo -e "${RED}✗ Failed to start services${NC}"
    exit 1
fi
echo ""

# Wait for services
echo -e "${YELLOW}Step 3: Waiting for services to be ready (90 seconds)...${NC}"
sleep 90
echo -e "${GREEN}✓ Services should be ready${NC}"
echo ""

# Initialize PostgreSQL
echo -e "${YELLOW}Step 4: Initializing PostgreSQL database...${NC}"
docker exec -i postgres psql -U envuser -d envdb < data/users.sql >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database initialized with 15 sample users${NC}"
else
    echo -e "${RED}✗ Database initialization failed${NC}"
    echo -e "${YELLOW}  You can try manually:${NC}"
    echo "  docker exec -i postgres psql -U envuser -d envdb < data/users.sql"
fi
echo ""

# Install Python dependencies
echo -e "${YELLOW}Step 5: Installing Python dependencies...${NC}"
pip3 install -r producers/requirements.txt --quiet
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Python dependencies installed${NC}"
else
    echo -e "${RED}✗ Failed to install Python dependencies${NC}"
fi
echo ""

# Create JDBC connector
echo -e "${YELLOW}Step 6: Creating PostgreSQL JDBC connector...${NC}"
sleep 10  # Extra wait for Kafka Connect
RESPONSE=$(curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/postgres-source.json \
  --silent --write-out "\n%{http_code}" 2>&1)

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
if [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ PostgreSQL connector created${NC}"
else
    echo -e "${RED}✗ Connector creation failed (HTTP $HTTP_CODE)${NC}"
    echo -e "${YELLOW}  Kafka Connect may not be ready yet.${NC}"
    echo -e "${YELLOW}  You can create it manually with:${NC}"
    echo "  curl -X POST http://localhost:8083/connectors -H \"Content-Type: application/json\" -d @connectors/postgres-source.json"
fi
echo ""

# Final summary
echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo -e "${BLUE}1. Start the NWS Weather Producer (Terminal 1):${NC}"
echo -e "   ${GREEN}python3 producers/nws_weather_producer.py${NC}"
echo ""
echo -e "${BLUE}2. Start the IoT Sensor Simulator (Terminal 2):${NC}"
echo -e "   ${GREEN}python3 producers/iot_sensor_simulator.py${NC}"
echo ""
echo -e "${YELLOW}   Or run both in background:${NC}"
echo -e "   ${GREEN}python3 producers/nws_weather_producer.py > weather.log 2>&1 &${NC}"
echo -e "   ${GREEN}python3 producers/iot_sensor_simulator.py > iot.log 2>&1 &${NC}"
echo ""
echo -e "${BLUE}3. Access ksqlDB CLI:${NC}"
echo -e "   ${GREEN}docker exec -it ksqldb-cli ksql http://ksqldb-server:8088${NC}"
echo ""
echo -e "${BLUE}4. Follow QUICKSTART.md for detailed instructions${NC}"
echo ""
echo -e "${YELLOW}Verify everything is running:${NC}"
echo "  curl http://localhost:8083/connectors  # Should list postgres-users-source"
echo "  docker-compose -f docker/docker-compose.yml ps  # All services Up"
echo ""
echo -e "${BLUE}============================================================${NC}"
echo ""
