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
# Production: real-time crypto data (Docker is the only prerequisite)
./run.sh                     # Default: spark_microbatch
./run.sh spark_streaming     # Spark streaming with windowed aggregations
./run.sh flink               # Flink true streaming

# Demo: synthetic stocks -> Spark -> console (no ClickHouse, no dashboard)
./run_demo.sh
```

Press `Ctrl+C` to stop all services.

## Production Pipeline

```text
./run.sh <consumer>
```

Runs the full production pipeline: **Coinbase crypto producer -> Kafka -> Consumer -> ClickHouse -> Web Dashboard (port 8502)**

| Consumer | Processing Model | Command |
|----------|-----------------|---------|
| **spark_microbatch** | Micro-batch (every 3 seconds) | `./run.sh` or `./run.sh spark_microbatch` |
| **spark_streaming** | Windowed aggregations + checkpoints | `./run.sh spark_streaming` |
| **flink** | True streaming (per record) | `./run.sh flink` |

- **Data**: Real-time crypto prices from Coinbase WebSocket (BTC, ETH, SOL, XRP, DOGE, LTC)
- **Dashboard**: Web/FastAPI at <http://localhost:8502>
- **Compose file**: `docker-compose.yml`

### Processing Engines

| Engine | Model | Latency | Best For |
|--------|-------|---------|----------|
| **spark_microbatch** | Micro-batch (every 3 seconds) | Seconds | Batch + streaming, ML pipelines |
| **spark_streaming** | Windowed aggregations + checkpoints | Seconds | Event-time processing, VWAP |
| **flink** | True streaming (per record) | Milliseconds | Real-time dashboards, alerts |

## Demo Pipeline

```bash
./run_demo.sh
```

Runs a minimal demo: **Synthetic stock producer -> Kafka -> Spark -> Console output**

- **Data**: Randomly generated stock prices (AAPL, GOOGL, MSFT, AMZN, META)
- **No ClickHouse, no dashboard** — just console output for learning
- **Compose file**: `docker-compose.demo.yml`

## Architecture

### Production

```text
+------------------+     +---------+     +-------------------+     +------------+     +-------------+
|                  |     |         |     |                   |     |            |     |             |
| crypto_producer  | --> |  Kafka  | --> | spark_microbatch  | --> | ClickHouse | --> | Web/FastAPI |
| (Coinbase)       |     |         |     | spark_streaming   |     |            |     |   (8502)    |
|                  |     |         |     | flink             |     |            |     |             |
+------------------+     +---------+     +-------------------+     +------------+     +-------------+
```

### Demo

```text
+---------------------+     +---------+     +-------------+
|                     |     |         |     |             |
| stock_producer_demo | --> |  Kafka  | --> | Spark       |
| (synthetic)         |     |         |     | (console)   |
+---------------------+     +---------+     +-------------+
```

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
# Real crypto (production)
python src/production/producer/crypto_producer.py

# OR Synthetic stocks (demo)
python src/demo/stock_producer_demo.py
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
python src/production/dashboard/web_app.py
```

**Terminal 4 - Query ClickHouse (optional):**

```bash
docker exec -it clickhouse clickhouse-client
```

```sql
SELECT * FROM stocks.ticks ORDER BY timestamp DESC LIMIT 10;
```

## Project Structure

```text
local_streaming_pipeline/
├── docker-compose.yml              # Production services (crypto + consumers + dashboard)
├── docker-compose.demo.yml         # Demo services (stock producer + Spark console)
├── run.sh                          # Production runner (one arg: consumer type)
├── run_demo.sh                     # Demo runner (no args)
├── requirements.txt                # Python dependencies (local dev)
├── lib/                            # Flink connector JARs
├── src/
│   ├── demo/
│   │   ├── Dockerfile.producer-demo        # Demo stock producer container
│   │   ├── Dockerfile.spark-consumer-demo  # Demo Spark console consumer container
│   │   ├── spark_consumer_demo.py          # Spark -> Console (learning/demo)
│   │   └── stock_producer_demo.py          # Synthetic stock data producer
│   └── production/
│       ├── consumer/
│       │   ├── Dockerfile.spark-consumer                  # Spark consumer container
│       │   ├── Dockerfile.flink-consumer                  # Flink consumer container
│       │   ├── flink_clickhouse_consumer.py               # Flink -> ClickHouse
│       │   ├── spark_microbatch_clickhouse_consumer.py    # Spark micro-batch -> ClickHouse
│       │   └── spark_streaming_clickhouse_consumer.py     # Spark streaming -> ClickHouse
│       ├── producer/
│       │   ├── Dockerfile.crypto-producer  # Crypto producer container
│       │   └── crypto_producer.py          # Real-time Coinbase WebSocket
│       └── dashboard/
│           ├── Dockerfile.web-dashboard  # FastAPI dashboard container
│           ├── web_app.py               # FastAPI web dashboard
│           └── static/
│               ├── stock_index.html     # Stock dashboard UI
│               └── crypto_index.html    # Crypto dashboard UI
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
lsof -i :8502  # Web dashboard
lsof -i :9092  # Kafka
```

### ClickHouse table not found

The `run.sh` script creates tables automatically. For manual runs, see the Local Development section.
