#!/bin/bash

# =============================================================================
# Local Streaming Pipeline Runner
# Starts: Producer -> Spark Consumer -> Streamlit Dashboard
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# PIDs for cleanup
PRODUCER_PID=""
SPARK_PID=""
STREAMLIT_PID=""

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"

    if [ -n "$STREAMLIT_PID" ]; then
        echo "Stopping Streamlit (PID: $STREAMLIT_PID)"
        kill $STREAMLIT_PID 2>/dev/null || true
    fi

    if [ -n "$SPARK_PID" ]; then
        echo "Stopping Spark consumer (PID: $SPARK_PID)"
        kill $SPARK_PID 2>/dev/null || true
    fi

    if [ -n "$PRODUCER_PID" ]; then
        echo "Stopping Producer (PID: $PRODUCER_PID)"
        kill $PRODUCER_PID 2>/dev/null || true
    fi

    echo -e "${GREEN}All processes stopped.${NC}"
    exit 0
}

# Set up trap for cleanup
trap cleanup SIGINT SIGTERM

# Print banner
echo -e "${GREEN}"
echo "=============================================="
echo "  Local Streaming Pipeline"
echo "  Kafka -> Spark -> ClickHouse -> Streamlit"
echo "=============================================="
echo -e "${NC}"

# Check if Docker containers are running
echo -e "${YELLOW}Checking Docker containers...${NC}"
if ! docker ps | grep -q kafka; then
    echo -e "${RED}Error: Kafka container not running. Start with: docker-compose up -d${NC}"
    exit 1
fi

if ! docker ps | grep -q clickhouse; then
    echo -e "${RED}Error: ClickHouse container not running. Start with: docker-compose up -d${NC}"
    exit 1
fi

echo -e "${GREEN}Docker containers are running.${NC}\n"

# Start Producer
echo -e "${YELLOW}Starting Producer...${NC}"
python src/producer/producer.py &
PRODUCER_PID=$!
echo -e "${GREEN}Producer started (PID: $PRODUCER_PID)${NC}\n"

# Wait a moment for producer to start sending data
sleep 2

# Start Spark Consumer
echo -e "${YELLOW}Starting Spark Consumer...${NC}"
python src/consumer/spark_clickhouse_consumer.py &
SPARK_PID=$!
echo -e "${GREEN}Spark Consumer started (PID: $SPARK_PID)${NC}\n"

# Wait for Spark to initialize
sleep 5

# Start Streamlit Dashboard
echo -e "${YELLOW}Starting Streamlit Dashboard...${NC}"
streamlit run src/dashboard/app.py --server.headless true &
STREAMLIT_PID=$!
echo -e "${GREEN}Streamlit started (PID: $STREAMLIT_PID)${NC}\n"

# Print status
echo -e "${GREEN}=============================================="
echo "  All services running!"
echo "=============================================="
echo -e "${NC}"
echo "  Producer:   PID $PRODUCER_PID"
echo "  Spark:      PID $SPARK_PID"
echo "  Streamlit:  PID $STREAMLIT_PID"
echo ""
echo -e "  Dashboard:  ${GREEN}http://localhost:8501${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for all background processes
wait
