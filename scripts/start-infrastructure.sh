#!/bin/bash
# GALILEO Infrastructure Startup Script
# Starts all core infrastructure services with health checks

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  GALILEO Infrastructure Startup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker installed${NC}"

if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose installed${NC}"

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running${NC}"
    echo -e "${YELLOW}Start Docker with: sudo systemctl start docker${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker daemon running${NC}"
echo ""

# Check for port conflicts
echo -e "${YELLOW}Checking for port conflicts...${NC}"
PORTS=(15432 16379 19000 19001 19090 19092 13001 15000 26686 14317)
CONFLICTS=()

for port in "${PORTS[@]}"; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        CONFLICTS+=($port)
    fi
done

if [ ${#CONFLICTS[@]} -gt 0 ]; then
    echo -e "${RED}❌ Port conflicts detected on: ${CONFLICTS[*]}${NC}"
    echo -e "${YELLOW}Stop services using these ports or modify docker-compose.infrastructure.yaml${NC}"
    exit 1
fi
echo -e "${GREEN}✓ No port conflicts${NC}"
echo ""

# Start infrastructure services
echo -e "${BLUE}Starting infrastructure services...${NC}"
docker compose -f docker-compose.infrastructure.yaml up -d

echo ""
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
echo ""

# Wait for PostgreSQL
echo -n "PostgreSQL: "
for i in {1..30}; do
    if docker compose -f docker-compose.infrastructure.yaml exec -T postgres pg_isready -U galileo &>/dev/null; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    sleep 2
    echo -n "."
done

# Wait for Redis
echo -n "Redis: "
for i in {1..15}; do
    if docker compose -f docker-compose.infrastructure.yaml exec -T redis redis-cli ping &>/dev/null; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    sleep 2
    echo -n "."
done

# Wait for MinIO
echo -n "MinIO: "
for i in {1..20}; do
    if curl -sf http://localhost:9000/minio/health/live &>/dev/null; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    sleep 2
    echo -n "."
done

# Wait for Kafka
echo -n "Kafka: "
for i in {1..30}; do
    if docker compose -f docker-compose.infrastructure.yaml exec -T kafka kafka-topics --bootstrap-server localhost:9092 --list &>/dev/null; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    sleep 2
    echo -n "."
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Infrastructure Services Started!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Display service URLs
echo -e "${BLUE}Service URLs (alternative ports to avoid conflicts):${NC}"
echo -e "  PostgreSQL:       ${YELLOW}localhost:15432${NC}"
echo -e "    User:           galileo"
echo -e "    Password:       galileo_dev_password"
echo -e "    Database:       galileo"
echo -e "    Connect:        psql -h localhost -p 15432 -U galileo galileo"
echo ""
echo -e "  Redis:            ${YELLOW}localhost:16379${NC}"
echo -e "    Connect:        redis-cli -h localhost -p 16379"
echo ""
echo -e "  MinIO Console:    ${YELLOW}http://localhost:19001${NC}"
echo -e "    User:           minioadmin"
echo -e "    Password:       minioadmin123"
echo ""
echo -e "  MinIO API:        ${YELLOW}http://localhost:19000${NC}"
echo ""
echo -e "  Kafka:            ${YELLOW}localhost:19092${NC}"
echo ""
echo -e "  Jaeger UI:        ${YELLOW}http://localhost:26686${NC}"
echo ""
echo -e "  Prometheus:       ${YELLOW}http://localhost:19090${NC}"
echo ""
echo -e "  Grafana:          ${YELLOW}http://localhost:13001${NC}"
echo -e "    User:           admin"
echo -e "    Password:       admin"
echo ""
echo -e "  MLflow:           ${YELLOW}http://localhost:15000${NC}"
echo ""
echo -e "${BLUE}📖 See PORTS.md for complete port mapping${NC}"
echo ""

# Show container status
echo -e "${BLUE}Container Status:${NC}"
docker compose -f docker-compose.infrastructure.yaml ps

echo ""
echo -e "${GREEN}To view logs: docker compose -f docker-compose.infrastructure.yaml logs -f${NC}"
echo -e "${GREEN}To stop: docker compose -f docker-compose.infrastructure.yaml down${NC}"
echo ""
