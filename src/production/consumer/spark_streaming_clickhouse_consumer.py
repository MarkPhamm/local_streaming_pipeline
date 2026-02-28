"""
Spark Structured Streaming Consumer -> ClickHouse (with Windowed Aggregations)

This consumer demonstrates core Spark Structured Streaming concepts:
  1. Event-time processing with watermarks
  2. Stateful windowed aggregations (tumbling windows)
  3. Fault tolerance via checkpointing

Architecture:
    Kafka (stock-ticks)
        |
        v
    df_parsed -> withWatermark("timestamp", "30 seconds")
        |
        +-> Stream 1: Raw ticks -> stocks.ticks (append, 3s trigger, checkpoint)
        |
        +-> Stream 2: 1-min windowed aggs -> stocks.ticks_1m_agg (update, 10s trigger, checkpoint)

Usage:
    python src/production/consumer/spark_streaming_clickhouse_consumer.py
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, to_timestamp, window, avg, min as spark_min,
    max as spark_max, sum as spark_sum, count as spark_count,
)
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType

# =============================================================================
# CONFIGURATION
# =============================================================================

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
KAFKA_TOPIC = "stock-ticks"

CLICKHOUSE_HOST = "localhost"
CLICKHOUSE_PORT = "8123"
CLICKHOUSE_DATABASE = "stocks"
CLICKHOUSE_RAW_TABLE = "ticks"
CLICKHOUSE_AGG_TABLE = "ticks_1m_agg"

# Streaming settings
RAW_BATCH_INTERVAL = "3 seconds"
AGG_BATCH_INTERVAL = "10 seconds"

# Watermark: how long to wait for late-arriving data before finalizing windows.
# Events arriving more than 30 seconds late (by event-time) will be dropped.
WATERMARK_DELAY = "30 seconds"

# Window duration for tumbling windows
WINDOW_DURATION = "1 minute"

# Checkpoint directories (one per stream for independent fault tolerance)
CHECKPOINT_DIR_RAW = "checkpoints/raw_ticks"
CHECKPOINT_DIR_AGG = "checkpoints/windowed_agg"

# =============================================================================
# CREATE SPARK SESSION
# =============================================================================

spark = (
    SparkSession.builder.appName("StockTickConsumer-Streaming")
    .config(
        "spark.jars.packages",
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
        "com.clickhouse:clickhouse-jdbc:0.6.0,"
        "org.apache.httpcomponents.client5:httpclient5:5.3.1",
    )
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

print("=" * 60)
print("Spark Structured Streaming Consumer (Windowed Aggregations)")
print(f"Reading from Kafka: {KAFKA_BOOTSTRAP_SERVERS}/{KAFKA_TOPIC}")
print(f"Raw ticks -> ClickHouse: {CLICKHOUSE_DATABASE}.{CLICKHOUSE_RAW_TABLE}")
print(f"Aggregations -> ClickHouse: {CLICKHOUSE_DATABASE}.{CLICKHOUSE_AGG_TABLE}")
print(f"Watermark delay: {WATERMARK_DELAY}")
print(f"Window duration: {WINDOW_DURATION}")
print("=" * 60)

# =============================================================================
# DEFINE SCHEMA FOR JSON MESSAGES
# =============================================================================

# Producer sends: {"symbol": "AAPL", "price": 150.25, "volume": 1000, "timestamp": "2026-01-30T10:30:00.123456"}
stock_schema = StructType([
    StructField("symbol", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("volume", LongType(), True),
    StructField("timestamp", StringType(), True),
])

# =============================================================================
# READ FROM KAFKA
# =============================================================================

df_raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", KAFKA_TOPIC)
    .option("startingOffsets", "latest")
    .load()
)

# =============================================================================
# PARSE JSON INTO COLUMNS
# =============================================================================

df_parsed = (
    df_raw
    .selectExpr("CAST(value AS STRING) as json_str")
    .select(from_json(col("json_str"), stock_schema).alias("data"))
    .select(
        col("data.symbol").alias("symbol"),
        col("data.price").alias("price"),
        col("data.volume").alias("volume"),
        to_timestamp(col("data.timestamp")).alias("timestamp"),
    )
    .filter(col("timestamp").isNotNull())
)

# =============================================================================
# EVENT-TIME PROCESSING: WATERMARK
# =============================================================================
#
# Watermarks tell Spark how long to wait for late-arriving data.
#
# Without a watermark, Spark would have to track ALL past windows forever
# (unbounded state). The watermark lets Spark drop state for windows that
# are older than (max event time seen - watermark delay).
#
# Example with WATERMARK_DELAY = "30 seconds":
#   - Spark sees event at 10:05:00 -> watermark = 10:04:30
#   - Any event with timestamp < 10:04:30 is considered "too late" and dropped
#   - Windows ending before 10:04:30 are finalized and their state is cleaned up

df_with_watermark = df_parsed.withWatermark("timestamp", WATERMARK_DELAY)

# =============================================================================
# CLICKHOUSE JDBC SETUP
# =============================================================================

CLICKHOUSE_JDBC_URL = f"jdbc:clickhouse://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DATABASE}"

CLICKHOUSE_PROPERTIES = {
    "driver": "com.clickhouse.jdbc.ClickHouseDriver",
    "user": "default",
    "password": "",
    "isolationLevel": "NONE",
}

# =============================================================================
# STREAM 1: RAW TICKS -> stocks.ticks
# =============================================================================

def write_raw_to_clickhouse(batch_df, batch_id):
    """Write raw tick data to ClickHouse (same as micro-batch consumer)."""
    row_count = batch_df.count()

    if row_count > 0:
        print(f"\n[Raw Batch {batch_id}] Writing {row_count} ticks to {CLICKHOUSE_RAW_TABLE}...")
        (
            batch_df.write
            .jdbc(
                url=CLICKHOUSE_JDBC_URL,
                table=CLICKHOUSE_RAW_TABLE,
                mode="append",
                properties=CLICKHOUSE_PROPERTIES,
            )
        )
        print(f"[Raw Batch {batch_id}] Done!")
    else:
        print(f"\n[Raw Batch {batch_id}] No new data")


raw_query = (
    df_with_watermark.writeStream
    .foreachBatch(write_raw_to_clickhouse)
    .outputMode("append")
    .trigger(processingTime=RAW_BATCH_INTERVAL)
    .option("checkpointLocation", CHECKPOINT_DIR_RAW)
    .queryName("raw_ticks_to_clickhouse")
    .start()
)

# =============================================================================
# STREAM 2: WINDOWED AGGREGATIONS -> stocks.ticks_1m_agg
# =============================================================================
#
# Tumbling window: non-overlapping, fixed-size time intervals.
# Each event belongs to exactly one window.
#
#   |----window 1----|----window 2----|----window 3----|
#   10:00           10:01           10:02           10:03
#
# To use SLIDING windows instead (overlapping), replace:
#   window(col("timestamp"), WINDOW_DURATION)
# with:
#   window(col("timestamp"), "1 minute", "30 seconds")
#   This creates 1-minute windows that slide every 30 seconds,
#   so each event belongs to TWO windows.

df_windowed = (
    df_with_watermark
    .groupBy(
        col("symbol"),
        window(col("timestamp"), WINDOW_DURATION),
    )
    .agg(
        # VWAP = Volume-Weighted Average Price = sum(price * volume) / sum(volume)
        # This gives more weight to prices where more shares traded.
        (spark_sum(col("price") * col("volume")) / spark_sum(col("volume"))).alias("vwap"),
        avg(col("price")).alias("avg_price"),
        spark_min(col("price")).alias("min_price"),
        spark_max(col("price")).alias("max_price"),
        spark_sum(col("volume")).alias("total_volume"),
        spark_count("*").alias("tick_count"),
    )
    .select(
        col("symbol"),
        col("window.start").alias("window_start"),
        col("window.end").alias("window_end"),
        col("vwap"),
        col("avg_price"),
        col("min_price"),
        col("max_price"),
        col("total_volume"),
        col("tick_count"),
    )
)


def write_agg_to_clickhouse(batch_df, batch_id):
    """
    Write windowed aggregations to ClickHouse.

    outputMode("update") means Spark sends updated rows for windows that are still open.
    ClickHouse's ReplacingMergeTree deduplicates on (symbol, window_start) during merges,
    keeping only the latest version of each row.

    To get deduplicated results immediately, query with FINAL:
        SELECT * FROM stocks.ticks_1m_agg FINAL ORDER BY window_start DESC
    """
    row_count = batch_df.count()

    if row_count > 0:
        print(f"\n[Agg Batch {batch_id}] Writing {row_count} window aggregations to {CLICKHOUSE_AGG_TABLE}...")
        (
            batch_df.write
            .jdbc(
                url=CLICKHOUSE_JDBC_URL,
                table=CLICKHOUSE_AGG_TABLE,
                mode="append",
                properties=CLICKHOUSE_PROPERTIES,
            )
        )
        print(f"[Agg Batch {batch_id}] Done!")
    else:
        print(f"\n[Agg Batch {batch_id}] No updated windows")


agg_query = (
    df_windowed.writeStream
    .foreachBatch(write_agg_to_clickhouse)
    .outputMode("update")
    .trigger(processingTime=AGG_BATCH_INTERVAL)
    .option("checkpointLocation", CHECKPOINT_DIR_AGG)
    .queryName("windowed_agg_to_clickhouse")
    .start()
)

# =============================================================================
# KEEP RUNNING (BOTH STREAMS)
# =============================================================================

print("\nStreaming consumer is running with 2 streams:")
print(f"  1. Raw ticks   -> {CLICKHOUSE_DATABASE}.{CLICKHOUSE_RAW_TABLE} (every {RAW_BATCH_INTERVAL})")
print(f"  2. 1-min aggs  -> {CLICKHOUSE_DATABASE}.{CLICKHOUSE_AGG_TABLE} (every {AGG_BATCH_INTERVAL})")
print("\nPress Ctrl+C to stop.\n")
print("To query aggregations in ClickHouse:")
print("  SELECT * FROM stocks.ticks_1m_agg FINAL ORDER BY window_start DESC LIMIT 10;")
print()

# awaitAnyTermination() blocks until any of the streaming queries terminates.
# If one fails, this will raise the exception so the process exits.
spark.streams.awaitAnyTermination()
