"""
Spark Streaming Consumer

This script reads stock tick messages from Kafka using Spark Structured Streaming.
It runs inside the Spark Docker container.
"""

from pyspark.sql import SparkSession

# =============================================================================
# CONFIGURATION
# =============================================================================

# Kafka connection (localhost when running on host machine)
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

# Topic to read from
KAFKA_TOPIC = "stock-ticks"

# How often to process batches (in seconds)
BATCH_INTERVAL = "3 seconds"

# =============================================================================
# CREATE SPARK SESSION
# =============================================================================

# SparkSession is the entry point to Spark
# - appName: name shown in Spark UI
# - spark.jars.packages: download Kafka connector JAR automatically
spark = (
    SparkSession.builder.appName("StockTickConsumer")
    .config(
        "spark.jars.packages",
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0",
    )
    .getOrCreate()
)

# Set log level to reduce noise (optional)
spark.sparkContext.setLogLevel("WARN")

print("=" * 60)
print("Spark Session Created")
print(f"Reading from: {KAFKA_BOOTSTRAP_SERVERS}")
print(f"Topic: {KAFKA_TOPIC}")
print(f"Batch interval: {BATCH_INTERVAL}")
print("=" * 60)

# =============================================================================
# READ FROM KAFKA
# =============================================================================

# readStream = continuous reading (streaming mode)
# format("kafka") = use Kafka as the source
df = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", KAFKA_TOPIC)
    .option("startingOffsets", "latest")  # Only read new messages
    .load()
)

# =============================================================================
# WHAT DOES KAFKA GIVE US?
# =============================================================================
#
# The DataFrame has these columns:
#   - key: message key (binary, often null)
#   - value: message content (binary) <-- our JSON is here!
#   - topic: topic name
#   - partition: partition number
#   - offset: message position
#   - timestamp: when Kafka received it
#
# Our JSON is in 'value' as bytes:
#   b'{"symbol": "AAPL", "price": 150.25, ...}'

# =============================================================================
# CONVERT VALUE FROM BYTES TO STRING
# =============================================================================

# Cast the binary 'value' column to string so we can read it
df_string = df.selectExpr("CAST(value AS STRING) as message")

# =============================================================================
# WRITE TO CONSOLE (OUTPUT)
# =============================================================================

# writeStream = continuous writing (streaming mode)
# format("console") = print to terminal
# trigger = how often to process (our 3 second batch)
query = (
    df_string.writeStream.outputMode("append")
    .format("console")
    .option("truncate", False)  # Show full message, don't cut off
    .trigger(processingTime=BATCH_INTERVAL)
    .start()
)

print("\nConsumer is running! Press Ctrl+C to stop.\n")

# =============================================================================
# KEEP RUNNING
# =============================================================================

# Wait for the stream to finish (runs forever until stopped)
query.awaitTermination()
