#!/bin/bash

# =============================================================================
# Demo Runner
#
# Spins up the demo pipeline: Kafka + stock producer + Spark console consumer
# No ClickHouse, no dashboard — just Kafka -> Spark -> Console output
#
# Usage:
#   ./run_demo.sh
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROFILES="--profile stock --profile demo"

# Cleanup on Ctrl+C
cleanup() {
    echo -e "\n${YELLOW}Shutting down all containers...${NC}"
    docker compose $PROFILES down
    echo -e "${GREEN}All containers stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Print banner
echo -e "${GREEN}"
echo "=============================================="
echo "  Demo Pipeline"
echo "  Kafka -> Spark -> Console (no ClickHouse)"
echo "=============================================="
echo -e "${NC}"

# Start Kafka and wait for health
echo -e "${YELLOW}Starting Kafka...${NC}"
docker compose up -d kafka

echo -e "${YELLOW}Waiting for Kafka to be ready...${NC}"
until docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null; do
    sleep 2
done
echo -e "${GREEN}Kafka is ready.${NC}"

# Create Kafka topic
echo -e "${YELLOW}Ensuring Kafka topic exists...${NC}"
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create --topic stock-ticks --partitions 1 --replication-factor 1 --if-not-exists 2>/dev/null
echo -e "${GREEN}Kafka topic ready.${NC}\n"

# Start demo services
echo -e "${GREEN}=============================================="
echo "  Starting demo services..."
echo -e "==============================================\n${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}\n"

docker compose $PROFILES up --build
