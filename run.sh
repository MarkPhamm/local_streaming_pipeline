#!/bin/bash

# =============================================================================
# Production Pipeline Runner (Fully Containerized)
#
# Runs: Crypto Producer (Coinbase) -> Kafka -> Consumer -> ClickHouse -> Web Dashboard
#
# Usage:
#   ./run.sh <consumer>
#
#   consumer: spark_microbatch (default) | spark_streaming | flink
#
# Examples:
#   ./run.sh                     # spark_microbatch
#   ./run.sh spark_microbatch    # same as above
#   ./run.sh spark_streaming     # spark streaming with windowed aggregations
#   ./run.sh flink               # flink true streaming
#
# For demo mode (synthetic stocks -> Spark -> console), use ./run_demo.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
CONSUMER="${1:-spark_microbatch}"

# Validate consumer
case $CONSUMER in
    spark_microbatch|spark_streaming|flink)
        ;;
    --help|-h)
        echo "Usage: ./run.sh <consumer>"
        echo ""
        echo "Consumer (pick one):"
        echo "  spark_microbatch  Spark micro-batch processing (default)"
        echo "  spark_streaming   Spark streaming with windowed aggregations"
        echo "  flink             Flink true streaming"
        echo ""
        echo "For demo mode (synthetic stocks), use: ./run_demo.sh"
        exit 0
        ;;
    *)
        echo -e "${RED}Error: Unknown consumer '$CONSUMER'${NC}"
        echo "Valid options: spark_microbatch, spark_streaming, flink"
        exit 1
        ;;
esac

# Build profile flags: consumer + crypto producer + web dashboard
PROFILES="--profile $CONSUMER --profile crypto --profile web"
export DASHBOARD_MODE=crypto

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
echo "  Production Pipeline (Containerized)"
case $CONSUMER in
    spark_microbatch)
        echo "  Kafka -> Spark (micro-batch) -> ClickHouse"
        ;;
    spark_streaming)
        echo "  Kafka -> Spark (streaming) -> ClickHouse"
        ;;
    flink)
        echo "  Kafka -> Flink -> ClickHouse"
        ;;
esac
echo -e "  Data: ${CYAN}Real-time Crypto (Coinbase)${GREEN}"
echo "  Dashboard: Web/FastAPI (port 8502)"
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

# Start all profiled services (blocks and streams logs)
echo -e "${GREEN}=============================================="
echo "  Starting all services..."
echo "==============================================\n${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}\n"

docker compose $PROFILES up --build
