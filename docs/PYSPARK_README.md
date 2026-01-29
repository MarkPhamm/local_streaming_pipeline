# PySpark Guide

## What is Spark?

Apache Spark is a **distributed data processing engine**. Think of it as a tool that can process huge amounts of data by splitting the work across multiple machines.

```text
Traditional (single machine):

  [1 million rows] --> [1 CPU] --> slow


Spark (distributed):

 [1 million rows] --> split --> [CPU 1] ─┐
                                [CPU 2] ─┼──> combine --> fast
                                [CPU 3] ─┘
```

## What is PySpark?

**PySpark** = Python API for Spark

```text
You write Python --> PySpark --> Spark Engine (Java/Scala)
                                      |
                                      v
                                 Does the work
```

You write Python code, PySpark translates it into Spark operations.

## Spark Modes

| Mode | Description |
| ---- | ----------- |
| **Batch** | Process all data at once (e.g., analyze last month's logs) |
| **Streaming** | Process data continuously as it arrives (what we're doing) |

## Spark Streaming: Micro-Batching

Spark Streaming doesn't process one message at a time. It uses **micro-batching**:

```text
Time:     0s      3s      6s      9s
          |-------|-------|-------|
Messages: m1 m2 m3|m4 m5 m6|m7 m8 m9|
          |       |       |       |
          v       v       v       v
        batch1  batch2  batch3  batch4
          |       |       |       |
          v       v       v       v
       process process process process
```

Every N seconds (we chose 3), Spark:

1. Grabs all new messages since last batch
2. Processes them together
3. Outputs results
4. Repeats

## How Spark Connects to Kafka

Spark needs a **connector** (JAR file) to talk to Kafka:

```text
+------------------+      +---------------------+      +-------+
|                  |      |                     |      |       |
|  Your PySpark    | ---> | Kafka Connector     | ---> | Kafka |
|  Code            |      | (spark-sql-kafka)   |      |       |
|                  |      |                     |      |       |
+------------------+      +---------------------+      +-------+
      Python               Java JAR file              Broker
```

The connector is downloaded automatically when you specify it in your Spark config.

## PySpark Streaming Concepts

### SparkSession

The entry point to Spark. You create one at the start:

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("MyApp") \
    .getOrCreate()
```

### DataFrame

Spark's main data structure. Like a table with rows and columns:

```text
+--------+-------+--------+
| symbol | price | volume |
+--------+-------+--------+
| AAPL   | 150.5 | 1000   |
| GOOGL  | 140.2 | 500    |
+--------+-------+--------+
```

### readStream

Tells Spark to read data continuously (streaming mode):

```python
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "stock-ticks") \
    .load()
```

### writeStream

Tells Spark where to output the processed data:

```python
query = df.writeStream \
    .outputMode("append") \
    .format("console") \
    .start()
```

## Kafka Message Format in Spark

When Spark reads from Kafka, it gets these columns:

| Column | Type | Description |
| ------ | ---- | ----------- |
| `key` | binary | Message key (often null) |
| `value` | binary | Message content (our JSON) |
| `topic` | string | Topic name |
| `partition` | int | Partition number |
| `offset` | long | Message position |
| `timestamp` | timestamp | When Kafka received it |

Our JSON is in the `value` column as bytes:

```text
value (bytes): b'{"symbol": "AAPL", "price": 150.5, ...}'
                          |
                          v
              Need to decode and parse
```

## Full Pipeline Diagram

```text
+-------------+       +-----------+       +------------------+
|             |       |           |       |                  |
| producer.py | ----> |   Kafka   | ----> | spark_consumer.py|
|             | send  |           | read  |                  |
+-------------+       +-----------+       +------------------+
      |                     |                     |
      v                     v                     v
  Generate             Store in            Every 3 seconds:
  stock tick           topic               - grab new messages
  every 1 sec          "stock-ticks"       - process batch
                                           - output results
```

## Docker Architecture

We run Spark inside Docker for a consistent environment (no Java install needed).

### Container Setup

```text
docker-compose.yml
├── kafka (container)    <-- message broker
└── spark (container)    <-- runs our PySpark consumer
         |
         └── mounts your code folder
             so it can run spark_consumer.py
```

### How It Works

```text
Your Machine                         Docker
+------------------+                +------------------+
|                  |                |                  |
| producer.py      | -------------> | Kafka container  |
| (runs locally)   |    send        | (port 9092)      |
|                  |                |                  |
+------------------+                +--------+---------+
                                             |
                                             | read
                                             v
                                    +------------------+
                                    |                  |
                                    | Spark container  |
                                    | (runs consumer)  |
                                    |                  |
                                    +------------------+
```

### Why Docker for Spark?

| Approach | Pros | Cons |
| -------- | ---- | ---- |
| **Local** | Simple, easy debug | Needs Java installed |
| **Docker** | No Java needed, consistent | More complex setup |

### Docker Networking (Important!)

Kafka needs **two listeners** because of how Docker networking works.

**The Problem:**

```text
producer.py -----> localhost:9092 -----> Kafka    ✅ Works
(your machine)

Spark container --> localhost:9092 --> ???        ❌ Fails!
(inside Docker)     (looks inside itself, not Kafka)
```

Inside the Spark container, `localhost` means the Spark container itself, not Kafka.

## The Solution: Two Ports

```text
Port 9092  = for connections from your machine (external)
Port 29092 = for connections from other Docker containers (internal)
```

```text
+--------------------------------------------------+
|                 Docker Network                   |
|                                                  |
|   Spark container                Kafka container |
|   +-------------+                +-------------+ |
|   |             |--- kafka:29092 -->|          | |
|   |   Spark     |                |   Kafka    | |
|   |             |                |            | |
|   +-------------+                +------+-----+ |
|                                         |       |
+-----------------------------------------|-------+
                                          | 9092
                                          | (exposed to outside)
                                          v
                                  +---------------+
                                  | Your Machine  |
                                  |               |
                                  | producer.py   |
                                  | localhost:9092|
                                  +---------------+
```

**Which port to use?**

| Running from | Connect to |
| ------------ | ---------- |
| Your machine (producer.py) | `localhost:9092` |
| Docker container (Spark) | `kafka:29092` |

Both ports go to the same Kafka broker - just different "doors".

## Required Dependencies

### Python Package

```text
pyspark
```

### Kafka Connector (JAR)

Specified when creating SparkSession:

```python
spark = SparkSession.builder \
    .appName("KafkaConsumer") \
    .config("spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
    .getOrCreate()
```

This tells Spark: "Download the Kafka connector JAR automatically"

The format is: `org.apache.spark:spark-sql-kafka-0-10_2.12:<spark-version>`

| Part | Meaning |
| ---- | ------- |
| `org.apache.spark` | Organization |
| `spark-sql-kafka-0-10` | Package name (Kafka 0.10+ protocol) |
| `2.12` | Scala version Spark is built with |
| `3.5.0` | Spark version (must match your PySpark) |

## Output Modes

When writing stream results, you choose an output mode:

| Mode | Description |
| ---- | ----------- |
| `append` | Only output new rows (most common) |
| `complete` | Output entire result table (for aggregations) |
| `update` | Only output changed rows |

For just consuming and printing, use `append`.

## Running the Consumer with spark-submit

### The Command

```bash
/opt/spark/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 /app/src/consumer/spark_consumer.py
```

### Breaking It Down

```text
/opt/spark/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 /app/src/consumer/spark_consumer.py
|__________________________|  |______|  |______________________________________________|  |__________________________________|
            |                    |                          |                                           |
      Spark's tool           Flag                   Kafka connector                            Your Python script
      to run apps                                   (Maven coordinates)                        (path inside container)
```

| Part | Meaning |
| ---- | ------- |
| `/opt/spark/bin/spark-submit` | Spark's CLI tool to run applications |
| `--packages` | Flag to download dependencies from Maven |
| `org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0` | Kafka connector JAR (auto-downloaded) |
| `/app/src/consumer/spark_consumer.py` | Path to your script inside the container |

### Why spark-submit?

You can't just run `python spark_consumer.py` because:

1. **Spark needs setup** - spark-submit configures the Spark environment
2. **Dependencies** - it downloads the Kafka connector JAR
3. **Cluster mode** - in production, it distributes work to workers

```text
python script.py          --> Just runs Python
spark-submit script.py    --> Sets up Spark, then runs Python with Spark context
```

### Why --packages?

The `--packages` flag tells Spark to:

1. Look up the package in Maven Central (like npm for Java)
2. Download the JAR file
3. Add it to the classpath

Without it, Spark wouldn't know how to talk to Kafka.

### Path Explanation

```text
Your machine:           /Users/you/project/src/consumer/spark_consumer.py
                                    |
                        mounted as volume in docker-compose.yml
                                    |
                                    v
Inside container:       /app/src/consumer/spark_consumer.py
```

The `-./:/app` volume mount maps your project folder to `/app` in the container.
