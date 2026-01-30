# Local Streaming Pipeline

A simple local streaming pipeline for learning purposes.

```text
Producer (Python) --> Kafka --> Spark Streaming --> ClickHouse
```

## Prerequisites

- Docker
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (Python package manager)

## Setup

### 1. Start Kafka

```bash
docker-compose up -d
```

Verify Kafka is running:

```bash
docker logs kafka
```

Look for: `Kafka Server started`

### 2. Create Python Virtual Environment

```bash
# Create virtual environment
uv venv

# Activate it
source .venv/bin/activate
```

Your prompt should now show `(.venv)` at the beginning.

### 3. Install Python Dependencies

```bash
uv pip install -r requirements.txt
```

### 4. Create Kafka Topic

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic stock-ticks \
  --partitions 1 \
  --replication-factor 1
```

## Project Structure

```text
local_streaming_pipeline/
├── docker-compose.yml       # Kafka + Spark + ClickHouse setup
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Project config + linting rules
├── src/
│   ├── producer/
│   │   └── producer.py      # Sends stock ticks to Kafka
│   └── consumer/
│       └── spark_consumer.py # Reads from Kafka with Spark
├── docs/
│   ├── KAFKA_README.md      # Kafka deep-dive documentation
│   ├── PYSPARK_README.md    # PySpark deep-dive documentation
│   └── CLICKHOUSE_README.md # ClickHouse deep-dive documentation
└── README.md                # This file
```

## Running the Pipeline

### 1. Start All Services

```bash
docker-compose up -d
```

### 2. Run the Producer (from your machine)

```bash
python src/producer/producer.py
```

### 3. Run the Spark Consumer (inside Spark container)

```bash
docker exec -it spark bash
/opt/spark/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 /app/src/consumer/spark_consumer.py
```

### 4. Query ClickHouse (inside ClickHouse container)

```bash
docker exec -it clickhouse clickhouse-client
```

```sql
SELECT * FROM stocks.ticks ORDER BY timestamp DESC LIMIT 10;
```

## Documentation

| Topic | Description |
| ----- | ----------- |
| [Kafka](docs/KAFKA_README.md) | Message broker concepts, topics, partitions, commands |
| [PySpark](docs/PYSPARK_README.md) | Structured Streaming, Kafka integration, spark-submit |
| [ClickHouse](docs/CLICKHOUSE_README.md) | Column storage, MergeTree engine, SQL queries |
