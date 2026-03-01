"""
Spark Streaming Consumer -> ClickHouse

This script reads stock tick messages from Kafka using Spark Structured Streaming
and writes them to ClickHouse for analytics.

It runs inside the Spark Docker container.

Usage:
    /opt/spark/bin/spark-submit \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.clickhouse:clickhouse-jdbc:0.6.0,org.apache.httpcomponents.client5:httpclient5:5.3.1 \
        /app/src/production/consumer/spark_microbatch_clickhouse_consumer.py
"""

import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, to_timestamp
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType

# =============================================================================
# CONFIGURATION
# =============================================================================

# Kafka connection (localhost when running on host machine)
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = "stock-ticks"

# ClickHouse connection (localhost when running on host machine)
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = os.environ.get("CLICKHOUSE_PORT", "8123")
CLICKHOUSE_DATABASE = "stocks"
CLICKHOUSE_TABLE = "ticks"

# How often to process batches (in seconds)
BATCH_INTERVAL = "3 seconds"

# =============================================================================
# CREATE SPARK SESSION
# =============================================================================

# We need TWO packages:
# 1. spark-sql-kafka: Read from Kafka
# 2. clickhouse-jdbc: Write to ClickHouse
spark = (
    SparkSession.builder.appName("StockTickConsumer-ClickHouse")
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
print("Spark Session Created")
print(f"Reading from Kafka: {KAFKA_BOOTSTRAP_SERVERS}/{KAFKA_TOPIC}")
print(f"Writing to ClickHouse: {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DATABASE}.{CLICKHOUSE_TABLE}")
print(f"Batch interval: {BATCH_INTERVAL}")
print("=" * 60)

# =============================================================================
# DEFINE SCHEMA FOR JSON MESSAGES
# =============================================================================

# Our producer sends JSON like:
# {"symbol": "AAPL", "price": 150.25, "volume": 1000, "timestamp": "2026-01-30T10:30:00.123456"}
#
# We need to tell Spark what fields to expect:

stock_schema = StructType([
    StructField("symbol", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("volume", LongType(), True),
    StructField("timestamp", StringType(), True),  # ISO format string from producer
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

# Kafka gives us: value = b'{"symbol": "AAPL", "price": 150.25, ...}'
# We need to:
# 1. Cast bytes to string
# 2. Parse JSON into columns

df_parsed = (
    df_raw
    # Cast binary value to string
    .selectExpr("CAST(value AS STRING) as json_str")
    # Parse JSON string into struct using our schema
    .select(from_json(col("json_str"), stock_schema).alias("data"))
    # Flatten: extract fields from the struct
    .select(
        col("data.symbol").alias("symbol"),
        col("data.price").alias("price"),
        col("data.volume").alias("volume"),
        # Convert ISO string to timestamp
        to_timestamp(col("data.timestamp")).alias("timestamp"),
    )
    # Filter out any rows with null values (malformed data)
    .filter(col("timestamp").isNotNull())
)

# =============================================================================
# WRITE TO CLICKHOUSE
# =============================================================================

# JDBC URL for ClickHouse
# Format: jdbc:clickhouse://host:port/database
CLICKHOUSE_JDBC_URL = f"jdbc:clickhouse://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DATABASE}"

# JDBC connection properties
# isolationLevel=NONE disables transaction isolation (ClickHouse doesn't support transactions)
CLICKHOUSE_PROPERTIES = {
    "driver": "com.clickhouse.jdbc.ClickHouseDriver",
    "user": "default",
    "password": "",
    "isolationLevel": "NONE",
}


def write_to_clickhouse(batch_df, batch_id):
    """
    Write a micro-batch to ClickHouse.

    This function is called for each micro-batch by foreachBatch.

    Args:
        batch_df: The DataFrame containing the micro-batch data
        batch_id: Unique identifier for this batch
    """
    # Count rows in this batch
    row_count = batch_df.count()

    if row_count > 0:
        print(f"\n[Batch {batch_id}] Writing {row_count} rows to ClickHouse...")

        # Write to ClickHouse using JDBC
        # mode("append") = add to existing data (don't overwrite)
        (
            batch_df.write
            .jdbc(
                url=CLICKHOUSE_JDBC_URL,
                table=CLICKHOUSE_TABLE,
                mode="append",
                properties=CLICKHOUSE_PROPERTIES,
            )
        )

        print(f"[Batch {batch_id}] Done!")
    else:
        print(f"\n[Batch {batch_id}] No new data")


# =============================================================================
# START THE STREAM
# =============================================================================

# foreachBatch: Process each micro-batch with our custom function
# This is how we write to destinations that don't have native Spark support

query = (
    df_parsed.writeStream
    .foreachBatch(write_to_clickhouse)
    .outputMode("append")
    .trigger(processingTime=BATCH_INTERVAL)
    .start()
)

print("\nConsumer is running! Press Ctrl+C to stop.\n")
print("To see data in ClickHouse, run:")
print("  docker exec -it clickhouse clickhouse-client")
print("  SELECT * FROM stocks.ticks ORDER BY timestamp DESC LIMIT 10;")
print()

# =============================================================================
# KEEP RUNNING
# =============================================================================

query.awaitTermination()
