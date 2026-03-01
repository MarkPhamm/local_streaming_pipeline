# Local Streaming Pipeline

<p align="center">
  <img src="assets/demo.gif" alt="Demo" width="100%" />
</p>

> A fully containerized streaming pipeline for learning real-time data processing with Kafka, Spark/Flink, and ClickHouse.
<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/83ec60e1-3b75-4e4c-baf7-4acfa4c9bbd4" />

```text
Producer --> Kafka --> Spark/Flink --> ClickHouse --> Dashboard
```

## Quick Start

```bash
# Clone and run (Docker is the only prerequisite)
./run.sh                           # Default: spark_microbatch + stock
./run.sh spark_streaming crypto    # Spark streaming + real-time crypto
./run.sh flink stock               # Flink + synthetic stocks
```

The `run.sh` script handles everything: starts infrastructure, creates Kafka topics, sets up ClickHouse tables, and launches all services in Docker containers.

Press `Ctrl+C` to stop all services.

## Run Options

```text
./run.sh <consumer> <data_source>
```

| Arg | Options | Default |
|-----|---------|---------|
| **consumer** | `spark_microbatch`, `spark_streaming`, `flink` | `spark_microbatch` |
| **data_source** | `stock`, `crypto` | `stock` |

### All Combinations

| Consumer | Data Source | Producer | Dashboard | Command |
|----------|------------|----------|-----------|---------|
| **spark_microbatch** | stock | Synthetic stocks | Streamlit (8501) | `./run.sh` |
| **spark_microbatch** | crypto | Coinbase WebSocket | Web/FastAPI (8502) | `./run.sh spark_microbatch crypto` |
| **spark_streaming** | stock | Synthetic stocks | Streamlit (8501) | `./run.sh spark_streaming stock` |
| **spark_streaming** | crypto | Coinbase WebSocket | Web/FastAPI (8502) | `./run.sh spark_streaming crypto` |
| **flink** | stock | Synthetic stocks | Streamlit (8501) | `./run.sh flink stock` |
| **flink** | crypto | Coinbase WebSocket | Web/FastAPI (8502) | `./run.sh flink crypto` |

### Data Sources

| Source | Description | Symbols | Dashboard |
|--------|-------------|---------|-----------|
| **stock** | Synthetic stock prices with volatile movements | AAPL, GOOGL, MSFT, AMZN, META | Streamlit (port 8501) |
| **crypto** | Live prices from Coinbase WebSocket (no API key needed) | BTC, ETH, SOL, XRP, DOGE, LTC | Web/FastAPI (port 8502) |

### Processing Engines

| Engine | Model | Latency | Best For |
|--------|-------|---------|----------|
| **spark_microbatch** | Micro-batch (every 3 seconds) | Seconds | Batch + streaming, ML pipelines |
| **spark_streaming** | Windowed aggregations + checkpoints | Seconds | Event-time processing, VWAP |
| **flink** | True streaming (per record) | Milliseconds | Real-time dashboards, alerts |

## Architecture

```text
+----------------------+     +-----------+     +-------------------+     +-------------+     +-------------+
|                      |     |           |     |                   |     |             |     |             |
| stock_producer_demo  | --> |   Kafka   | --> | spark_microbatch  | --> | ClickHouse  | --> | Streamlit   |
| (synthetic, demo)    |     |           |     | spark_streaming   |     |             |     |   (8501)    |
|         OR           |     |           |     | flink             |     |             |     |      OR     |
| crypto_producer      |     |           |     |                   |     |             |     | Web/FastAPI |
| (Coinbase, live)     |     |           |     |                   |     |             |     |   (8502)    |
+----------------------+     +-----------+     +-------------------+     +-------------+     +-------------+
```

All components run as Docker containers orchestrated via `docker compose` profiles.

## Prerequisites

- Docker

That's it. Everything runs in containers.

For **local development** (running scripts outside Docker), you also need:
- Python 3.10+
- Java 11+ (for Flink)
- [uv](https://github.com/astral-sh/uv) (Python package manager)

## Local Development (Optional)

If you prefer running components manually outside Docker:

### Setup

```bash
# 1. Start infrastructure
docker compose up -d kafka clickhouse

# 2. Install dependencies
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 3. Create Kafka topic
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic stock-ticks --partitions 1 --replication-factor 1

# 4. Create ClickHouse tables
docker exec clickhouse clickhouse-client --query "CREATE DATABASE IF NOT EXISTS stocks"
docker exec clickhouse clickhouse-client --query "
    CREATE TABLE IF NOT EXISTS stocks.ticks (
        symbol String, price Float64, volume UInt32, timestamp DateTime64(6)
    ) ENGINE = MergeTree() ORDER BY (symbol, timestamp)
"
```

### Run Manually (Separate Terminals)

**Terminal 1 - Producer:**

```bash
# Synthetic stocks
python src/demo/stock_producer_demo.py

# OR Real crypto
python src/production/producer/crypto_producer.py
```

**Terminal 2 - Consumer:**

```bash
# Spark micro-batch
python src/production/consumer/spark_microbatch_clickhouse_consumer.py

# OR Spark streaming (windowed aggregations)
python src/production/consumer/spark_streaming_clickhouse_consumer.py

# OR Flink (true streaming)
python src/production/consumer/flink_clickhouse_consumer.py
```

**Terminal 3 - Dashboard:**

```bash
# Web dashboard (FastAPI)
python src/production/dashboard/web_app.py

# OR Streamlit
streamlit run src/production/dashboard/app.py
```

**Terminal 4 - Query ClickHouse (optional):**

```bash
docker exec -it clickhouse clickhouse-client
```

```sql
SELECT * FROM stocks.ticks ORDER BY timestamp DESC LIMIT 10;
```

### Dashboard URLs

| Dashboard | URL |
|-----------|-----|
| Streamlit | <http://localhost:8501> |
| Web (FastAPI) | <http://localhost:8502> |

## Project Structure

```text
local_streaming_pipeline/
├── docker-compose.yml          # All services with Docker Compose profiles
├── run.sh                      # Pipeline runner (two args: consumer + data_source)
├── requirements.txt            # Python dependencies (local dev)
├── lib/                        # Flink connector JARs
├── src/
│   ├── demo/
│   │   ├── Dockerfile                # Demo producer container
│   │   ├── Dockerfile.spark-demo     # Demo Spark consumer container
│   │   ├── spark_consumer_demo.py    # Spark -> Console (learning/demo)
│   │   └── stock_producer_demo.py    # Synthetic stock data producer
│   └── production/
│       ├── consumer/
│       │   ├── Dockerfile.spark                           # Spark consumer container
│       │   ├── Dockerfile.flink                           # Flink consumer container
│       │   ├── flink_clickhouse_consumer.py               # Flink -> ClickHouse
│       │   ├── spark_microbatch_clickhouse_consumer.py    # Spark micro-batch -> ClickHouse
│       │   └── spark_streaming_clickhouse_consumer.py     # Spark streaming -> ClickHouse
│       ├── producer/
│       │   ├── Dockerfile              # Crypto producer container
│       │   └── crypto_producer.py      # Real-time Coinbase WebSocket
│       └── dashboard/
│           ├── Dockerfile              # Dashboard container (Streamlit + FastAPI)
│           ├── app.py                  # Streamlit dashboard
│           ├── web_app.py              # FastAPI web dashboard
│           └── static/
│               ├── stock_index.html    # Stock dashboard UI
│               └── crypto_index.html   # Crypto dashboard UI
├── docs/
│   ├── KAFKA_README.md         # Kafka concepts & commands
│   ├── PYSPARK_README.md       # PySpark streaming guide
│   ├── SPARK_STREAMING_README.md # Spark streaming guide
│   ├── FLINK_README.md         # Flink streaming guide
│   └── CLICKHOUSE_README.md    # ClickHouse analytics guide
└── README.md                   # This file
```

## Documentation

| Topic | Description |
| ----- | ----------- |
| [Kafka](docs/KAFKA_README.md) | Message broker concepts, topics, partitions, commands |
| [PySpark](docs/PYSPARK_README.md) | Structured Streaming, micro-batching, Kafka integration |
| [Spark Streaming](docs/SPARK_STREAMING_README.md) | Watermarks, windowed aggregations, checkpointing, VWAP |
| [Flink](docs/FLINK_README.md) | True streaming, PyFlink, Kafka & ClickHouse integration |
| [ClickHouse](docs/CLICKHOUSE_README.md) | Column storage, MergeTree engine, SQL queries |

## Troubleshooting

### Containers not starting

```bash
docker compose ps -a          # Check container status
docker compose logs <service> # Check specific service logs
```

### Orphan containers from previous runs

```bash
docker compose down --remove-orphans
```

### Port already in use

```bash
lsof -i :8501  # Streamlit
lsof -i :8502  # Web dashboard
lsof -i :9092  # Kafka
```

### ClickHouse table not found

The `run.sh` script creates tables automatically. For manual runs, see the Local Development section.
