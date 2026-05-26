#!/bin/bash
echo "Checking running containers..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep galileo

echo -e "\n================================"
echo "Checking API Gateway logs..."
echo "================================"
docker logs galileo-v20-api-gateway-1 --tail 50

echo -e "\n================================"
echo "Checking if all services are up..."
echo "================================"
docker compose -f docker-compose.microservices.yaml ps | grep -E "(ml-service|inversion-service|control-service|api-gateway)"
