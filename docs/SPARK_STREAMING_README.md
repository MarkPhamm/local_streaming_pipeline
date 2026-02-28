# Spark Structured Streaming: Windowed Aggregations & Checkpointing

This guide covers the advanced Spark Structured Streaming concepts implemented in `spark_streaming_clickhouse_consumer.py`.

## Table of Contents

- [Event-Time vs Processing-Time](#event-time-vs-processing-time)
- [Watermarks and Late Data](#watermarks-and-late-data)
- [Windowed Aggregations](#windowed-aggregations)
- [VWAP (Volume-Weighted Average Price)](#vwap-volume-weighted-average-price)
- [Checkpointing and Fault Tolerance](#checkpointing-and-fault-tolerance)
- [ReplacingMergeTree and FINAL Queries](#replacingmergetree-and-final-queries)
- [Example ClickHouse Queries](#example-clickhouse-queries)

---

## Event-Time vs Processing-Time

| Concept | Definition | Example |
|---------|-----------|---------|
| **Event-time** | When the event actually happened (embedded in the data) | `"timestamp": "2026-01-30T10:30:00"` |
| **Processing-time** | When Spark processes the event | Wall clock on the Spark executor |

**Why event-time matters:** In real systems, events can arrive out of order or late (network delays, retries, etc.). If you aggregate by processing-time, a late event gets placed in the wrong window. Event-time aggregation places events in the correct window based on when they actually occurred.

```
Event-time:      10:00:01  10:00:02  10:00:03  10:00:01 (late!)
Processing-time: 10:00:05  10:00:06  10:00:07  10:00:08

With event-time windows, the late event at 10:00:01 goes into the 10:00-10:01 window (correct).
With processing-time, it would go into the 10:00-10:01 processing window (wrong context).
```

Our consumer uses event-time via the `timestamp` field from the Kafka messages.

---

## Watermarks and Late Data

A **watermark** tells Spark: "I don't expect to see events older than X."

```python
df.withWatermark("timestamp", "30 seconds")
```

This means:
- Spark tracks the maximum event-time it has seen so far
- The watermark = `max_event_time - 30 seconds`
- Any event with a timestamp older than the watermark is dropped
- Windows that end before the watermark are finalized and their state is cleaned up

### How it works step by step

```
1. Spark sees event at 10:05:00  -> watermark = 10:04:30
2. Spark sees event at 10:05:10  -> watermark = 10:04:40
3. Event arrives at  10:04:35   -> ACCEPTED (10:04:35 > 10:04:30 watermark at step 1)
4. Event arrives at  10:04:25   -> DROPPED  (10:04:25 < 10:04:40 current watermark)
```

### Why watermarks are necessary

Without watermarks, Spark would keep ALL window state forever (unbounded memory). Watermarks let Spark discard old state, making streaming queries sustainable for long-running jobs.

### Choosing a watermark delay

| Delay | Trade-off |
|-------|-----------|
| Short (5s) | Less memory, but more late data dropped |
| Long (5min) | Keeps more state, accepts more late data |
| Our choice (30s) | Good balance for local stock tick pipeline |

---

## Windowed Aggregations

### Tumbling Windows (what we use)

Non-overlapping, fixed-size time intervals. Each event belongs to exactly one window.

```
|---window 1---|---window 2---|---window 3---|
10:00         10:01         10:02         10:03

Event at 10:00:30 -> window 1
Event at 10:01:15 -> window 2
```

```python
# Tumbling window: 1-minute, no overlap
window(col("timestamp"), "1 minute")
```

### Sliding Windows (alternative)

Overlapping windows. Each event can belong to multiple windows.

```
|------window A------|
     |------window B------|
          |------window C------|
10:00    10:00:30   10:01    10:01:30   10:02

Event at 10:00:45 -> belongs to window A AND window B
```

```python
# Sliding window: 1-minute duration, slides every 30 seconds
window(col("timestamp"), "1 minute", "30 seconds")
```

### Our aggregation query

```python
df_with_watermark.groupBy(
    col("symbol"),
    window(col("timestamp"), "1 minute"),  # tumbling window
).agg(
    vwap, avg_price, min_price, max_price, total_volume, tick_count
)
```

This produces one row per `(symbol, window)` combination. For 5 stock symbols, each minute produces 5 aggregation rows.

---

## VWAP (Volume-Weighted Average Price)

VWAP gives more weight to prices where more volume was traded. It's a standard financial metric.

```
VWAP = sum(price * volume) / sum(volume)
```

### Example

| Tick | Price | Volume | price * volume |
|------|-------|--------|----------------|
| 1 | $100 | 1000 | $100,000 |
| 2 | $102 | 5000 | $510,000 |
| 3 | $99 | 500 | $49,500 |

```
Simple average = ($100 + $102 + $99) / 3 = $100.33
VWAP = ($100,000 + $510,000 + $49,500) / (1000 + 5000 + 500) = $101.46
```

VWAP is closer to $102 because that's where most of the volume traded.

### In Spark

```python
(spark_sum(col("price") * col("volume")) / spark_sum(col("volume"))).alias("vwap")
```

---

## Checkpointing and Fault Tolerance

Checkpoints save the state of a streaming query so it can resume from where it left off after a failure or restart.

### What gets checkpointed

1. **Kafka offsets** - Which messages have been read
2. **Aggregation state** - Current window values (partial sums, counts)
3. **Watermark position** - Current watermark value

### Checkpoint directory structure

```
checkpoints/
├── raw_ticks/          # Stream 1: raw tick writes
│   ├── offsets/        # Kafka offsets per micro-batch
│   ├── commits/        # Completed batch markers
│   └── metadata        # Query metadata
└── windowed_agg/       # Stream 2: aggregation writes
    ├── offsets/
    ├── commits/
    ├── state/          # Window aggregation state (RocksDB)
    └── metadata
```

### Why each stream needs its own checkpoint

Each streaming query tracks its own Kafka offsets and state independently. Sharing a checkpoint directory between two queries would cause conflicts and data corruption.

### Fault tolerance guarantees

| Guarantee | Description |
|-----------|-------------|
| **Exactly-once source** | Kafka offsets in checkpoint ensure no re-reads |
| **At-least-once sink** | JDBC writes may duplicate on crash recovery |
| **Effective exactly-once** | ReplacingMergeTree deduplicates at query time |

### Resuming after restart

```bash
# Stop the consumer (Ctrl+C)
# Restart it - checkpoints allow seamless resumption
./run.sh spark streaming web

# Spark reads checkpoint -> resumes from last committed Kafka offset
# No data loss, no reprocessing of already-committed batches
```

---

## ReplacingMergeTree and FINAL Queries

### The problem

Our aggregation stream uses `outputMode("update")`, which means Spark re-emits updated rows for windows that are still open. This results in multiple rows for the same `(symbol, window_start)` in ClickHouse.

### The solution: ReplacingMergeTree

```sql
CREATE TABLE stocks.ticks_1m_agg (
    ...
) ENGINE = ReplacingMergeTree()
ORDER BY (symbol, window_start)
```

ReplacingMergeTree keeps only the **latest version** of each row (identified by the ORDER BY key) when ClickHouse runs background merges.

### Querying with FINAL

Background merges happen asynchronously. To get deduplicated results immediately, use `FINAL`:

```sql
-- May return duplicates (pre-merge)
SELECT * FROM stocks.ticks_1m_agg ORDER BY window_start DESC LIMIT 10;

-- Always deduplicated (forces merge at query time)
SELECT * FROM stocks.ticks_1m_agg FINAL ORDER BY window_start DESC LIMIT 10;
```

**Note:** `FINAL` adds query overhead. For dashboards querying frequently, the duplicates from recent windows are usually acceptable and resolve on the next merge.

---

## Example ClickHouse Queries

Connect to ClickHouse:

```bash
docker exec -it clickhouse clickhouse-client
```

### View latest aggregations

```sql
SELECT *
FROM stocks.ticks_1m_agg FINAL
ORDER BY window_start DESC
LIMIT 20;
```

### VWAP vs average price comparison

```sql
SELECT
    symbol,
    window_start,
    round(vwap, 2) AS vwap,
    round(avg_price, 2) AS avg_price,
    round(vwap - avg_price, 4) AS vwap_vs_avg_diff,
    tick_count
FROM stocks.ticks_1m_agg FINAL
ORDER BY window_start DESC
LIMIT 20;
```

### Highest volume windows

```sql
SELECT
    symbol,
    window_start,
    total_volume,
    tick_count,
    round(vwap, 2) AS vwap
FROM stocks.ticks_1m_agg FINAL
ORDER BY total_volume DESC
LIMIT 10;
```

### Price spread per window (volatility indicator)

```sql
SELECT
    symbol,
    window_start,
    round(max_price - min_price, 4) AS spread,
    round((max_price - min_price) / avg_price * 100, 2) AS spread_pct,
    tick_count
FROM stocks.ticks_1m_agg FINAL
ORDER BY spread_pct DESC
LIMIT 10;
```

### Compare raw ticks to aggregation

```sql
-- Raw ticks in a specific minute
SELECT symbol, price, volume, timestamp
FROM stocks.ticks
WHERE symbol = 'AAPL'
  AND timestamp >= '2026-01-30 10:00:00'
  AND timestamp < '2026-01-30 10:01:00'
ORDER BY timestamp;

-- Corresponding aggregation
SELECT *
FROM stocks.ticks_1m_agg FINAL
WHERE symbol = 'AAPL'
  AND window_start = '2026-01-30 10:00:00';
```
