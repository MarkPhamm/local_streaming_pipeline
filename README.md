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
├── docker-compose.yml    # Kafka setup
├── requirements.txt      # Python dependencies
├── docs/
│   └── KAFKA_README.md   # Kafka deep-dive documentation
└── README.md             # This file
```

## Documentation

- [Kafka Deep Dive](docs/KAFKA_README.md) - Detailed Kafka concepts and commands
