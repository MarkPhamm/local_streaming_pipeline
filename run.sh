#!/bin/bash

# =============================================================================
# Local Streaming Pipeline Runner (Fully Containerized)
# All components run via docker compose with profiles.
#
# Usage:
#   ./run.sh                         # Default: synthetic + Spark micro-batch + Streamlit
#   ./run.sh spark                   # Spark (micro-batch) + Streamlit
#   ./run.sh spark streaming         # Spark (streaming + windowed aggs) + Streamlit
#   ./run.sh spark web               # Spark + Web dashboard
#   ./run.sh flink                   # Flink + Streamlit
#   ./run.sh flink web               # Flink + Web dashboard
#   ./run.sh --crypto                # Crypto (forces Web dashboard)
#   ./run.sh spark streaming --crypto # Spark streaming + crypto + Web
#   ./run.sh flink --crypto          # Flink + crypto + Web
#
# Note: --crypto always uses the Web dashboard (Streamlit can't render fast enough)
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
SPARK_MODE="microbatch"
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
        streaming)
            SPARK_MODE="streaming"
            ;;
        --crypto|crypto)
            DATA_SOURCE="crypto"
            ;;
        --synthetic|synthetic)
            DATA_SOURCE="synthetic"
            ;;
        --help|-h)
            echo "Usage: ./run.sh [spark|flink] [streaming] [streamlit|web] [--crypto|--synthetic]"
            echo ""
            echo "Options:"
            echo "  spark       Use Spark Structured Streaming (micro-batch, default)"
            echo "  streaming   Use Spark with windowed aggregations + checkpointing"
            echo "  flink       Use Flink (true streaming)"
            echo "  streamlit   Use Streamlit dashboard (port 8501, default)"
            echo "  web         Use FastAPI web dashboard (port 8502)"
            echo "  --crypto    Use real-time crypto data (forces web dashboard)"
            echo "  --synthetic Use synthetic stock data (default)"
            exit 0
            ;;
    esac
done

# Build profile flags
PROFILES=""

# Producer profile
if [ "$DATA_SOURCE" == "crypto" ]; then
    PROFILES="$PROFILES --profile crypto"
else
    PROFILES="$PROFILES --profile synthetic"
fi

# Consumer profile
if [ "$CONSUMER_TYPE" == "spark" ] && [ "$SPARK_MODE" == "streaming" ]; then
    PROFILES="$PROFILES --profile spark-streaming"
elif [ "$CONSUMER_TYPE" == "spark" ]; then
    PROFILES="$PROFILES --profile spark-microbatch"
else
    PROFILES="$PROFILES --profile flink"
fi

# Crypto forces web dashboard (Streamlit can't render fast enough)
if [ "$DATA_SOURCE" == "crypto" ] && [ "$DASHBOARD_TYPE" == "streamlit" ]; then
    echo -e "${YELLOW}Note: Crypto mode uses the Web dashboard (Streamlit can't keep up with real-time data)${NC}"
    DASHBOARD_TYPE="web"
fi

# Dashboard profile
PROFILES="$PROFILES --profile $DASHBOARD_TYPE"

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down all containers...${NC}"
    docker compose $PROFILES down
    echo -e "${GREEN}All containers stopped.${NC}"
    exit 0
}

# Set up trap for cleanup
trap cleanup SIGINT SIGTERM

# Print banner
echo -e "${GREEN}"
echo "=============================================="
echo "  Local Streaming Pipeline (Containerized)"
if [ "$CONSUMER_TYPE" == "spark" ] && [ "$SPARK_MODE" == "streaming" ]; then
    echo "  Kafka -> Spark -> ClickHouse"
    echo "  (streaming + windowed aggregations)"
elif [ "$CONSUMER_TYPE" == "spark" ]; then
    echo "  Kafka -> Spark -> ClickHouse"
    echo "  (micro-batch processing)"
else
    echo "  Kafka -> Flink -> ClickHouse"
    echo "  (true streaming)"
fi
if [ "$DASHBOARD_TYPE" == "streamlit" ]; then
    echo "  Dashboard: Streamlit (http://localhost:8501)"
else
    echo "  Dashboard: Web/FastAPI (http://localhost:8502)"
fi
if [ "$DATA_SOURCE" == "crypto" ]; then
    echo -e "  Data: ${CYAN}Real-time Crypto (Coinbase)${GREEN}"
else
    echo "  Data: Synthetic stocks"
fi
echo "=============================================="
echo -e "${NC}"

# Start infrastructure and wait for health
echo -e "${YELLOW}Starting infrastructure (Kafka + ClickHouse)...${NC}"
docker compose up -d kafka clickhouse

echo -e "${YELLOW}Waiting for Kafka to be ready...${NC}"
until docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null; do
    sleep 2
done
echo -e "${GREEN}Kafka is ready.${NC}"

echo -e "${YELLOW}Waiting for ClickHouse to be ready...${NC}"
until docker exec clickhouse clickhouse-client --query "SELECT 1" 2>/dev/null; do
    sleep 2
done
echo -e "${GREEN}ClickHouse is ready.${NC}"

# Create Kafka topic (if not exists)
echo -e "${YELLOW}Ensuring Kafka topic exists...${NC}"
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create --topic stock-ticks --partitions 1 --replication-factor 1 --if-not-exists 2>/dev/null
echo -e "${GREEN}Kafka topic ready.${NC}"

# Create ClickHouse database and tables (if not exists)
echo -e "${YELLOW}Ensuring ClickHouse tables exist...${NC}"
docker exec clickhouse clickhouse-client --query "CREATE DATABASE IF NOT EXISTS stocks"
docker exec clickhouse clickhouse-client --query "
    CREATE TABLE IF NOT EXISTS stocks.ticks (
        symbol String,
        price Float64,
        volume UInt32,
        timestamp DateTime64(6)
    ) ENGINE = MergeTree()
    ORDER BY (symbol, timestamp)
"
docker exec clickhouse clickhouse-client --query "
    CREATE TABLE IF NOT EXISTS stocks.ticks_1m_agg (
        symbol String,
        window_start DateTime64(6),
        window_end DateTime64(6),
        vwap Float64,
        avg_price Float64,
        min_price Float64,
        max_price Float64,
        total_volume UInt64,
        tick_count UInt32
    ) ENGINE = ReplacingMergeTree()
    ORDER BY (symbol, window_start)
"
echo -e "${GREEN}ClickHouse tables ready.${NC}\n"

# Set DASHBOARD_MODE for crypto
if [ "$DATA_SOURCE" == "crypto" ]; then
    export DASHBOARD_MODE=crypto
fi

# Start all profiled services (blocks and streams logs)
echo -e "${GREEN}=============================================="
echo "  Starting all services..."
echo "==============================================\n${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}\n"

docker compose $PROFILES up --build
