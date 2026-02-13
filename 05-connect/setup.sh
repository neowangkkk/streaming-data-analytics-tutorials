#!/bin/bash

echo "======================================"
echo "ksqlDB Multi-Source Tutorial Setup"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"
command -v docker >/dev/null 2>&1 || { echo "Docker not found. Please install Docker."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose not found. Please install Docker Compose."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 not found. Please install Python 3."; exit 1; }
echo -e "${GREEN}✓ All prerequisites found${NC}"
echo ""

echo -e "${YELLOW}Step 2: Starting Docker services...${NC}"
docker-compose -f docker/docker-compose.yml up -d
echo -e "${GREEN}✓ Services started${NC}"
echo ""

echo -e "${YELLOW}Step 3: Waiting for services to be ready (60 seconds)...${NC}"
sleep 60
echo -e "${GREEN}✓ Services should be ready${NC}"
echo ""

echo -e "${YELLOW}Step 4: Initializing PostgreSQL...${NC}"
docker exec -i postgres psql -U envuser -d envdb < data/users.sql
echo -e "${GREEN}✓ Database initialized with sample users${NC}"
echo ""

echo -e "${YELLOW}Step 5: Installing Python dependencies...${NC}"
pip3 install -r producers/requirements.txt --quiet
echo -e "${GREEN}✓ Python dependencies installed${NC}"
echo ""

echo -e "${YELLOW}Step 6: Creating Kafka Connect connectors...${NC}"
echo "Creating weather connector..."
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/weather-source.json \
  --silent --output /dev/null
echo -e "${GREEN}✓ Weather connector created${NC}"

echo "Creating postgres connector..."
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/postgres-source.json \
  --silent --output /dev/null
echo -e "${GREEN}✓ Postgres connector created${NC}"
echo ""

echo "======================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Start the IoT simulator:"
echo "   python3 producers/iot_sensor_simulator.py &"
echo ""
echo "2. Access ksqlDB CLI:"
echo "   docker exec -it ksqldb-cli ksql http://ksqldb-server:8088"
echo ""
echo "3. Follow QUICKSTART.md for detailed instructions"
echo ""
