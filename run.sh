#!/bin/bash

# =============================================================================
# Local Streaming Pipeline Runner
# Starts: Producer -> Consumer (Spark or Flink) -> Dashboard (Streamlit or Web)
#
# Usage:
#   ./run.sh                    # Default: Spark + Streamlit
#   ./run.sh spark              # Spark + Streamlit
#   ./run.sh flink              # Flink + Streamlit
#   ./run.sh spark web          # Spark + Web dashboard
#   ./run.sh flink web          # Flink + Web dashboard
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Consumer type (default: spark)
CONSUMER_TYPE="${1:-spark}"

# Dashboard type (default: streamlit)
DASHBOARD_TYPE="${2:-streamlit}"

# Validate consumer type
if [[ "$CONSUMER_TYPE" != "spark" && "$CONSUMER_TYPE" != "flink" ]]; then
    echo -e "${RED}Error: Invalid consumer type '$CONSUMER_TYPE'${NC}"
    echo "Usage: ./run.sh [spark|flink] [streamlit|web]"
    exit 1
fi

# Validate dashboard type
if [[ "$DASHBOARD_TYPE" != "streamlit" && "$DASHBOARD_TYPE" != "web" ]]; then
    echo -e "${RED}Error: Invalid dashboard type '$DASHBOARD_TYPE'${NC}"
    echo "Usage: ./run.sh [spark|flink] [streamlit|web]"
    exit 1
fi

# PIDs for cleanup
PRODUCER_PID=""
CONSUMER_PID=""
DASHBOARD_PID=""

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"

    if [ -n "$DASHBOARD_PID" ]; then
        echo "Stopping $DASHBOARD_TYPE dashboard (PID: $DASHBOARD_PID)"
        kill $DASHBOARD_PID 2>/dev/null || true
    fi

    if [ -n "$CONSUMER_PID" ]; then
        echo "Stopping $CONSUMER_TYPE consumer (PID: $CONSUMER_PID)"
        kill $CONSUMER_PID 2>/dev/null || true
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
if [ "$CONSUMER_TYPE" == "spark" ]; then
    echo "  Kafka -> Spark -> ClickHouse"
    echo "  (micro-batch processing)"
else
    echo "  Kafka -> Flink -> ClickHouse"
    echo "  (true streaming)"
fi
if [ "$DASHBOARD_TYPE" == "streamlit" ]; then
    echo "  Dashboard: Streamlit (port 8501)"
else
    echo "  Dashboard: Web/FastAPI (port 8502)"
fi
echo "=============================================="
echo -e "${NC}"

# Check if Docker containers are running
echo -e "${YELLOW}Checking Docker containers...${NC}"
if ! docker ps | grep -q kafka; then
    echo -e "${RED}Error: Kafka container not running. Start with: docker compose up -d${NC}"
    exit 1
fi

if ! docker ps | grep -q clickhouse; then
    echo -e "${RED}Error: ClickHouse container not running. Start with: docker compose up -d${NC}"
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

# Start Consumer (Spark or Flink)
if [ "$CONSUMER_TYPE" == "spark" ]; then
    echo -e "${YELLOW}Starting Spark Consumer (micro-batch)...${NC}"
    python src/consumer/spark_clickhouse_consumer.py &
    CONSUMER_PID=$!
    echo -e "${GREEN}Spark Consumer started (PID: $CONSUMER_PID)${NC}\n"
    # Wait for Spark to initialize
    sleep 5
else
    echo -e "${YELLOW}Starting Flink Consumer (true streaming)...${NC}"
    python src/consumer/flink_clickhouse_consumer.py &
    CONSUMER_PID=$!
    echo -e "${GREEN}Flink Consumer started (PID: $CONSUMER_PID)${NC}\n"
    # Wait for Flink to initialize
    sleep 3
fi

# Start Dashboard (Streamlit or Web)
if [ "$DASHBOARD_TYPE" == "streamlit" ]; then
    echo -e "${YELLOW}Starting Streamlit Dashboard...${NC}"
    streamlit run src/dashboard/app.py --server.headless true &
    DASHBOARD_PID=$!
    DASHBOARD_URL="http://localhost:8501"
    echo -e "${GREEN}Streamlit started (PID: $DASHBOARD_PID)${NC}\n"
else
    echo -e "${YELLOW}Starting Web Dashboard (FastAPI)...${NC}"
    python src/dashboard/web_app.py &
    DASHBOARD_PID=$!
    DASHBOARD_URL="http://localhost:8502"
    echo -e "${GREEN}Web dashboard started (PID: $DASHBOARD_PID)${NC}\n"
fi

# Print status
echo -e "${GREEN}=============================================="
echo "  All services running!"
echo "=============================================="
echo -e "${NC}"
echo "  Producer:   PID $PRODUCER_PID"
if [ "$CONSUMER_TYPE" == "spark" ]; then
    echo -e "  Consumer:   PID $CONSUMER_PID ${BLUE}(Spark)${NC}"
else
    echo -e "  Consumer:   PID $CONSUMER_PID ${BLUE}(Flink)${NC}"
fi
if [ "$DASHBOARD_TYPE" == "streamlit" ]; then
    echo -e "  Dashboard:  PID $DASHBOARD_PID ${BLUE}(Streamlit)${NC}"
else
    echo -e "  Dashboard:  PID $DASHBOARD_PID ${BLUE}(Web/FastAPI)${NC}"
fi
echo ""
echo -e "  Dashboard:  ${GREEN}${DASHBOARD_URL}${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for all background processes
wait
