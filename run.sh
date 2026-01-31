#!/bin/bash

# =============================================================================
# Local Streaming Pipeline Runner
# Starts: Producer -> Consumer (Spark or Flink) -> Dashboard (Streamlit or Web)
#
# Usage:
#   ./run.sh                         # Default: synthetic + Spark + Streamlit
#   ./run.sh spark                   # Spark + Streamlit
#   ./run.sh flink                   # Flink + Streamlit
#   ./run.sh spark web               # Spark + Web dashboard
#   ./run.sh flink web               # Flink + Web dashboard
#   ./run.sh --crypto                # Use real crypto data (Binance)
#   ./run.sh flink web --crypto      # Flink + Web + real crypto data
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
CONSUMER_TYPE="spark"
DASHBOARD_TYPE="streamlit"
DATA_SOURCE="synthetic"

# Parse arguments
for arg in "$@"; do
    case $arg in
        spark)
            CONSUMER_TYPE="spark"
            ;;
        flink)
            CONSUMER_TYPE="flink"
            ;;
        streamlit)
            DASHBOARD_TYPE="streamlit"
            ;;
        web)
            DASHBOARD_TYPE="web"
            ;;
        --crypto|crypto)
            DATA_SOURCE="crypto"
            ;;
        --synthetic|synthetic)
            DATA_SOURCE="synthetic"
            ;;
        --help|-h)
            echo "Usage: ./run.sh [spark|flink] [streamlit|web] [--crypto|--synthetic]"
            echo ""
            echo "Options:"
            echo "  spark       Use Spark Structured Streaming (micro-batch)"
            echo "  flink       Use Flink (true streaming)"
            echo "  streamlit   Use Streamlit dashboard (port 8501)"
            echo "  web         Use FastAPI web dashboard (port 8502)"
            echo "  --crypto    Use real-time crypto data from Coinbase"
            echo "  --synthetic Use synthetic stock data (default)"
            exit 0
            ;;
    esac
done

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
        echo "Stopping producer (PID: $PRODUCER_PID)"
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
if [ "$DATA_SOURCE" == "crypto" ]; then
    echo -e "  Data: ${CYAN}Real-time Crypto (Coinbase)${GREEN}"
else
    echo "  Data: Synthetic stocks"
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
if [ "$DATA_SOURCE" == "crypto" ]; then
    echo -e "${YELLOW}Starting Crypto Producer (Coinbase WebSocket)...${NC}"
    python src/producer/crypto_producer.py &
    PRODUCER_PID=$!
    echo -e "${GREEN}Crypto Producer started (PID: $PRODUCER_PID)${NC}\n"
else
    echo -e "${YELLOW}Starting Synthetic Producer...${NC}"
    python src/producer/producer.py &
    PRODUCER_PID=$!
    echo -e "${GREEN}Synthetic Producer started (PID: $PRODUCER_PID)${NC}\n"
fi

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
    if [ "$DATA_SOURCE" == "crypto" ]; then
        echo -e "${YELLOW}Starting Crypto Web Dashboard (FastAPI)...${NC}"
        python src/dashboard/web_app.py --crypto &
    else
        echo -e "${YELLOW}Starting Stock Web Dashboard (FastAPI)...${NC}"
        python src/dashboard/web_app.py &
    fi
    DASHBOARD_PID=$!
    DASHBOARD_URL="http://localhost:8502"
    echo -e "${GREEN}Web dashboard started (PID: $DASHBOARD_PID)${NC}\n"
fi

# Print status
echo -e "${GREEN}=============================================="
echo "  All services running!"
echo "=============================================="
echo -e "${NC}"
if [ "$DATA_SOURCE" == "crypto" ]; then
    echo -e "  Producer:   PID $PRODUCER_PID ${CYAN}(Coinbase Crypto)${NC}"
else
    echo -e "  Producer:   PID $PRODUCER_PID ${BLUE}(Synthetic)${NC}"
fi
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
