# ClickHouse Guide

## What is ClickHouse?

ClickHouse is a **column-oriented database** optimized for analytics and real-time queries.

### Row vs Column Storage

```text
Traditional DB (row-based):          ClickHouse (column-based):

| symbol | price | volume |          symbol: [AAPL, GOOGL, MSFT, AMZN, ...]
|--------|-------|--------|          price:  [150.5, 140.2, 380.0, 175.0, ...]
| AAPL   | 150.5 | 1000   |          volume: [1000, 500, 2000, 800, ...]
| GOOGL  | 140.2 | 500    |
| MSFT   | 380.0 | 2000   |
| AMZN   | 175.0 | 800    |
```

### Why Column Storage?

Query: "What's the average price?"

```text
Row-based:
  Read: [AAPL, 150.5, 1000], [GOOGL, 140.2, 500], ...
        ^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^
        Reads ALL columns even though we only need price

Column-based:
  Read: price: [150.5, 140.2, 380.0, 175.0]
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        Only reads the price column = FASTER
```

## Why ClickHouse for Our Project?

| Feature | Benefit |
| ------- | ------- |
| **Fast inserts** | Handle millions of stock ticks |
| **Fast aggregations** | Quick AVG, SUM, COUNT queries |
| **Time-series optimized** | Perfect for timestamped data |
| **Compression** | Column storage compresses well |
| **SQL interface** | Familiar query language |

## Architecture in Our Pipeline

```text
+-------------+       +-----------+       +------------------+       +-------------+
|             |       |           |       |                  |       |             |
| stock_producer.py | ----> |   Kafka   | ----> | spark_consumer.py| ----> | ClickHouse  |
|             |       |           |       |                  |       |             |
+-------------+       +-----------+       +------------------+       +-------------+
     |                     |                     |                         |
     v                     v                     v                         v
  Generate             Store in            Process every              Store for
  stock ticks          topic               3 seconds                  analytics
```

## Docker Configuration

### Ports

```yaml
ports:
  - "8123:8123"    # HTTP interface
  - "9000:9000"    # Native TCP interface
```

| Port | Protocol | Used For |
| ---- | -------- | -------- |
| 8123 | HTTP | Browser queries, REST API, curl |
| 9000 | Native TCP | Spark, Python drivers, clickhouse-client |

### Volumes

```yaml
volumes:
  - clickhouse_data:/var/lib/clickhouse
```

Data is stored in a **named volume** so it persists when the container restarts.

```text
Without volume:                    With volume:

docker-compose down                docker-compose down
     |                                  |
     v                                  v
Data is LOST                       Data is KEPT
                                   (stored in clickhouse_data)
```

### Environment Variables

```yaml
environment:
  CLICKHOUSE_USER: default
  CLICKHOUSE_PASSWORD: ""
  CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1
```

| Variable | Value | Meaning |
| -------- | ----- | ------- |
| `CLICKHOUSE_USER` | default | Username for connections |
| `CLICKHOUSE_PASSWORD` | "" | No password (dev only!) |
| `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT` | 1 | Allow user management |

## Connecting to ClickHouse

### From Inside Docker (Spark)

```text
Host: clickhouse
Port: 9000 (native) or 8123 (HTTP)
```

### From Your Machine

```text
Host: localhost
Port: 9000 (native) or 8123 (HTTP)
```

### Connection Diagram

```text
+--------------------------------------------------+
|                 Docker Network                   |
|                                                  |
|   Spark container              ClickHouse        |
|   +-------------+              +-------------+   |
|   |             |--- clickhouse:9000 -->|    |   |
|   |   Spark     |              | ClickHouse |   |
|   |             |              |            |   |
|   +-------------+              +------+-----+   |
|                                       |         |
+---------------------------------------|----------+
                                        | 8123, 9000
                                        v
                                +---------------+
                                | Your Machine  |
                                | localhost:8123|
                                +---------------+
```

## Commands

### Start ClickHouse

```bash
docker-compose up -d clickhouse
```

### Check Logs

```bash
docker logs clickhouse
```

### Connect with CLI (inside container)

```bash
docker exec -it clickhouse clickhouse-client
```

### Connect with CLI (from your machine via HTTP)

```bash
curl "http://localhost:8123/?query=SELECT%201"
```

## SQL Basics

### Create a Database

```sql
CREATE DATABASE IF NOT EXISTS stocks;
```

### Create a Table for Stock Ticks

```sql
CREATE TABLE IF NOT EXISTS stocks.ticks (
    symbol String,
    price Float64,
    volume UInt32,
    timestamp DateTime64(6)
) ENGINE = MergeTree()
ORDER BY (symbol, timestamp);
```

**Explanation:**

| Part | Meaning |
| ---- | ------- |
| `String` | Text type (like VARCHAR) |
| `Float64` | 64-bit decimal number |
| `UInt32` | Unsigned 32-bit integer |
| `DateTime64(6)` | Timestamp with microsecond precision |
| `ENGINE = MergeTree()` | ClickHouse's main table engine (fast!) |
| `ORDER BY (symbol, timestamp)` | How data is sorted/indexed |

### Insert Data

```sql
INSERT INTO stocks.ticks VALUES
    ('AAPL', 150.50, 1000, now()),
    ('GOOGL', 140.25, 500, now());
```

### Query Data

```sql
-- Get all ticks
SELECT * FROM stocks.ticks;

-- Average price per symbol
SELECT symbol, avg(price) as avg_price
FROM stocks.ticks
GROUP BY symbol;

-- Last 10 ticks
SELECT * FROM stocks.ticks
ORDER BY timestamp DESC
LIMIT 10;
```

## MergeTree Engine

ClickHouse has many table engines. **MergeTree** is the most common:

```text
MergeTree:
+------------------+
| Incoming Data    |
+--------+---------+
         |
         v
+--------+---------+
| Small Parts      |  <-- Data written in small chunks
+--------+---------+
         |
         | (background merge)
         v
+--------+---------+
| Large Parts      |  <-- Merged into larger, sorted parts
+------------------+

Benefits:
- Fast inserts (just append)
- Fast reads (data is sorted)
- Automatic optimization
```

## ClickHouse vs Other Databases

| Database | Type | Best For |
| -------- | ---- | -------- |
| **ClickHouse** | Column OLAP | Analytics, aggregations, time-series |
| PostgreSQL | Row OLTP | Transactions, CRUD operations |
| MongoDB | Document | Flexible schemas, JSON data |
| Redis | Key-Value | Caching, sessions |

## Useful Queries for Our Project

### Count ticks per symbol

```sql
SELECT symbol, count() as tick_count
FROM stocks.ticks
GROUP BY symbol
ORDER BY tick_count DESC;
```

### Price stats per symbol

```sql
SELECT
    symbol,
    min(price) as min_price,
    max(price) as max_price,
    avg(price) as avg_price
FROM stocks.ticks
GROUP BY symbol;
```

### Ticks in last 5 minutes

```sql
SELECT *
FROM stocks.ticks
WHERE timestamp > now() - INTERVAL 5 MINUTE
ORDER BY timestamp DESC;
```

### Volume weighted average price (VWAP)

```sql
SELECT
    symbol,
    sum(price * volume) / sum(volume) as vwap
FROM stocks.ticks
GROUP BY symbol;
```
