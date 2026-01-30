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
│   ├── consumer/
│   │   ├── spark_consumer.py            # Reads from Kafka, prints to console
│   │   └── spark_clickhouse_consumer.py # Reads from Kafka, writes to ClickHouse
│   └── dashboard/
│       └── app.py                       # Streamlit dashboard
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

Verify all containers are running:

```bash
docker ps
```

You should see:

```text
NAMES        IMAGE                              STATUS
kafka        apache/kafka:3.7.0                 Up
spark        apache/spark:3.5.0                 Up
clickhouse   clickhouse/clickhouse-server:24.1  Up
```

### 2. Run the Pipeline (4 Terminals)

| Terminal | What | Command |
|----------|------|---------|
| 1 | Producer | `python src/producer/producer.py` |
| 2 | Console consumer | See below |
| 3 | ClickHouse consumer | See below |
| 4 | Query ClickHouse | `docker exec -it clickhouse clickhouse-client` |

**Terminal 2 - Console consumer:**

```bash
docker exec -it spark /opt/spark/bin/spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/src/consumer/spark_consumer.py
```

**Terminal 3 - ClickHouse consumer:**

```bash
docker exec -it spark /opt/spark/bin/spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.clickhouse:clickhouse-jdbc:0.6.0,org.apache.httpcomponents.client5:httpclient5:5.3.1 \
  /app/src/consumer/spark_clickhouse_consumer.py
```

**Terminal 4 - Query ClickHouse:**

```bash
docker exec -it clickhouse clickhouse-client
```

```sql
SELECT * FROM stocks.ticks ORDER BY timestamp DESC LIMIT 10;
```

### Flow Diagram

```text
docker-compose up -d
        |
        v
+-------+-------+------------+
|       |       |            |
v       v       v            v
Kafka  Spark  ClickHouse   (all running)

Then:

                      +-> spark_consumer.py -----------> Console (print)
                      |
Producer -> Kafka ----+
                      |
                      +-> spark_clickhouse_consumer.py -> ClickHouse (store)
                                                              |
                                                              v
                                                         Streamlit Dashboard
```

### 5. Run the Dashboard (from your machine)

```bash
streamlit run src/dashboard/app.py
```

Opens at <http://localhost:8501>

## Documentation

| Topic | Description |
| ----- | ----------- |
| [Kafka](docs/KAFKA_README.md) | Message broker concepts, topics, partitions, commands |
| [PySpark](docs/PYSPARK_README.md) | Structured Streaming, Kafka integration, spark-submit |
| [ClickHouse](docs/CLICKHOUSE_README.md) | Column storage, MergeTree engine, SQL queries |
