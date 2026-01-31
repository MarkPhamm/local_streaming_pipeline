# Apache Flink Guide

## What is Flink?

Apache Flink is a **distributed stream processing engine**. Unlike Spark which uses micro-batching, Flink processes data **one record at a time** as it arrives (true streaming).

```text
Spark Streaming (micro-batch):

  Messages:  m1 m2 m3 | m4 m5 m6 | m7 m8 m9
             |________|  |________|  |________|
             batch 1     batch 2     batch 3
               |           |           |
               v           v           v
            process     process     process
            (delay)     (delay)     (delay)


Flink (true streaming):

  Messages:  m1 → m2 → m3 → m4 → m5 → m6 → m7 → m8 → m9
             |    |    |    |    |    |    |    |    |
             v    v    v    v    v    v    v    v    v
          process each record immediately (low latency)
```

## Why Flink Over Spark for This Project?

| Feature | Spark Streaming | Flink |
| ------- | --------------- | ----- |
| **Processing Model** | Micro-batch (every N seconds) | True streaming (per record) |
| **Latency** | Seconds (batch interval) | Milliseconds |
| **Exactly-once** | Yes (with checkpoints) | Yes (with checkpoints) |
| **State Management** | Limited | Advanced (built-in) |
| **Best For** | Batch + some streaming | Real-time streaming |

For a stock ticker dashboard where we want to see prices update in real-time, Flink's low latency is ideal.

## PyFlink

**PyFlink** = Python API for Flink

```text
You write Python --> PyFlink --> Flink Engine (Java)
                                      |
                                      v
                                 Processes data
```

PyFlink lets you write Flink applications in Python instead of Java/Scala.

## Full Pipeline Architecture

```text
+-------------+       +-----------+       +---------------------+       +-------------+       +-------------+
|             |       |           |       |                     |       |             |       |             |
| producer.py | ----> |   Kafka   | ----> | flink_consumer.py   | ----> | ClickHouse  | ----> |   Web App   |
|             | send  |           | read  |                     | write |             | query |  (FastAPI)  |
+-------------+       +-----------+       +---------------------+       +-------------+       +-------------+
      |                     |                      |                          |                     |
      v                     v                      v                          v                     v
   Generate             Store in             Process each              Store for              Serve dashboard
   stock tick           topic                record instantly          analytics              & API endpoints
   every 1 sec          "stock-ticks"        write to ClickHouse       & queries              to browser
```

## Data Flow Step by Step

### 1. Producer → Kafka

The producer generates fake stock ticks and sends them to Kafka:

```text
producer.py
    |
    |  {"symbol": "AAPL", "price": 150.50, "volume": 1000, "timestamp": "..."}
    |
    v
Kafka topic: stock-ticks
    [msg1] [msg2] [msg3] [msg4] ...
```

### 2. Kafka → Flink

Flink continuously reads from Kafka using a `KafkaSource`:

```text
Kafka topic: stock-ticks
    |
    | KafkaSource (streaming)
    |
    v
Flink DataStream
    m1 → m2 → m3 → m4 → ...
```

### 3. Flink → ClickHouse

Each record is processed by a `MapFunction` that writes to ClickHouse:

```text
Flink DataStream
    |
    | ClickHouseSinkFunction.map()
    |   - Parse JSON
    |   - Insert into ClickHouse
    |
    v
ClickHouse table: stocks.ticks
    +--------+-------+--------+---------------------+
    | symbol | price | volume | timestamp           |
    +--------+-------+--------+---------------------+
    | AAPL   | 150.5 | 1000   | 2024-01-30 10:00:01 |
    | GOOGL  | 140.2 | 500    | 2024-01-30 10:00:02 |
    | ...    | ...   | ...    | ...                 |
    +--------+-------+--------+---------------------+
```

### 4. ClickHouse → Web App

The FastAPI web app queries ClickHouse and serves the dashboard:

```text
ClickHouse
    |
    | SQL queries (latest prices, history, stats)
    |
    v
FastAPI (web_app.py)
    |
    | /api/latest   - Latest price per symbol
    | /api/history  - Price history for charts
    | /api/recent   - Most recent ticks
    | /api/stats    - Price statistics
    |
    v
Browser (index.html)
    - Real-time charts
    - Price cards
    - Recent ticks table
```

## Flink Concepts

### StreamExecutionEnvironment

The entry point to a Flink application:

```python
from pyflink.datastream import StreamExecutionEnvironment

env = StreamExecutionEnvironment.get_execution_environment()
```

### KafkaSource

Reads data from Kafka topics:

```python
from pyflink.datastream.connectors.kafka import KafkaSource

kafka_source = (
    KafkaSource.builder()
    .set_bootstrap_servers("localhost:9092")
    .set_topics("stock-ticks")
    .set_group_id("flink-consumer")
    .set_starting_offsets(KafkaOffsetsInitializer.latest())
    .set_value_only_deserializer(SimpleStringSchema())
    .build()
)
```

### MapFunction

Transforms each record in the stream:

```python
from pyflink.datastream.functions import MapFunction

class MyMapper(MapFunction):
    def map(self, value):
        # Process each record
        return transformed_value
```

### Checkpointing

Enables fault tolerance by periodically saving state:

```python
env.enable_checkpointing(10000)  # Every 10 seconds
```

If Flink crashes, it can recover from the last checkpoint.

## Connector JARs

Flink needs JAR files to connect to external systems like Kafka:

```text
+------------------+      +---------------------+      +-------+
|                  |      |                     |      |       |
|  Your PyFlink    | ---> | Kafka Connector     | ---> | Kafka |
|  Code            |      | (JAR file)          |      |       |
|                  |      |                     |      |       |
+------------------+      +---------------------+      +-------+
      Python               lib/ directory              Broker
```

The connector JAR is loaded at startup:

```python
KAFKA_JAR = f"file://{LIB_DIR}/flink-sql-connector-kafka-3.2.0-1.19.jar"
env.add_jars(KAFKA_JAR)
```

## Running the Pipeline

### Prerequisites

1. **Java 11** installed
2. **Kafka** running (via docker-compose)
3. **ClickHouse** running (via docker-compose)
4. **Python dependencies** installed:
   ```bash
   pip install apache-flink==1.20.0 clickhouse-connect kafka-python
   ```

### Start Infrastructure

```bash
docker-compose up -d kafka clickhouse
```

### Create ClickHouse Table

```bash
docker exec -it clickhouse clickhouse-client
```

```sql
CREATE DATABASE IF NOT EXISTS stocks;

CREATE TABLE IF NOT EXISTS stocks.ticks (
    symbol String,
    price Float64,
    volume UInt32,
    timestamp DateTime64(6)
) ENGINE = MergeTree()
ORDER BY (symbol, timestamp);
```

### Start Components (in separate terminals)

```bash
# Terminal 1: Producer
python src/producer/producer.py

# Terminal 2: Flink Consumer
python src/consumer/flink_clickhouse_consumer.py

# Terminal 3: Web Dashboard
python src/dashboard/web_app.py
```

### View Dashboard

Open http://localhost:8502 in your browser.

## Flink vs Spark: When to Use Which

| Scenario | Recommendation |
| -------- | -------------- |
| Real-time dashboards | **Flink** (low latency) |
| Alerting on live data | **Flink** (immediate processing) |
| ETL with some streaming | **Spark** (unified batch/stream) |
| Complex event processing | **Flink** (better state management) |
| Machine learning pipelines | **Spark** (MLlib integration) |

## Troubleshooting

### "Java not found"

Flink requires Java 11. Install it and set `JAVA_HOME`:

```bash
# macOS with Homebrew
brew install openjdk@11
export JAVA_HOME=$(/usr/libexec/java_home -v 11)
```

### "Connection refused" to Kafka

Make sure Kafka is running:

```bash
docker-compose up -d kafka
docker logs kafka
```

### "Table not found" in ClickHouse

Create the database and table first (see above).

### Flink job exits immediately

Check for errors in the console output. Common issues:
- Missing JAR files in `lib/` directory
- ClickHouse not running
- Wrong Kafka topic name
