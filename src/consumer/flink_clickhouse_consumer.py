"""
Flink Streaming Consumer -> ClickHouse

This script reads stock tick messages from Kafka using Flink
and writes them to ClickHouse in real-time (true streaming, not micro-batches).

Unlike Spark Structured Streaming which processes in micro-batches,
Flink processes each record as it arrives.

Requirements:
    - Java 11 installed
    - PyFlink: pip install apache-flink==1.20.0
    - Connector JARs in lib/ directory (Kafka)
    - clickhouse-connect for ClickHouse writes

Usage:
    python src/consumer/flink_clickhouse_consumer.py
"""

import os

from pyflink.common import SimpleStringSchema, WatermarkStrategy
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import (
    KafkaOffsetsInitializer,
    KafkaSource,
)
from pyflink.datastream.functions import MapFunction, RuntimeContext

# =============================================================================
# CONFIGURATION
# =============================================================================

# Get project root directory (two levels up from this script)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PROJECT_ROOT, "lib")

# Connector JARs required for Kafka
KAFKA_JAR = f"file://{LIB_DIR}/flink-sql-connector-kafka-3.2.0-1.19.jar"

# Kafka connection (localhost when running on host machine)
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
KAFKA_TOPIC = "stock-ticks"
KAFKA_GROUP_ID = "flink-clickhouse-consumer"

# ClickHouse connection
CLICKHOUSE_HOST = "localhost"
CLICKHOUSE_PORT = 8123
CLICKHOUSE_DATABASE = "stocks"
CLICKHOUSE_TABLE = "ticks"

# =============================================================================
# CLICKHOUSE SINK MAP FUNCTION
# =============================================================================


class ClickHouseSinkFunction(MapFunction):
    """Map function that writes records to ClickHouse.

    The client is created in open() so it's not serialized with the function.
    """

    def __init__(self, host: str, port: int, database: str, table: str):
        self.host = host
        self.port = port
        self.database = database
        self.table = table
        self.client = None

    def open(self, runtime_context: RuntimeContext):
        """Called when the function is initialized on the worker."""
        import clickhouse_connect
        self.client = clickhouse_connect.get_client(
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def close(self):
        """Called when the function is torn down."""
        if self.client:
            self.client.close()

    def map(self, value: str) -> str:
        """Process each record and write to ClickHouse."""
        import json
        from datetime import datetime
        try:
            data = json.loads(value)
            # Parse ISO timestamp string to datetime for DateTime64 column
            ts = datetime.fromisoformat(data["timestamp"])
            self.client.insert(
                self.table,
                [[data["symbol"], data["price"], data["volume"], ts]],
                column_names=["symbol", "price", "volume", "timestamp"],
            )
        except Exception as e:
            print(f"Error writing to ClickHouse: {e}")
        return value


# =============================================================================
# CREATE FLINK STREAMING ENVIRONMENT
# =============================================================================

# Create streaming environment
env = StreamExecutionEnvironment.get_execution_environment()

# Add Kafka connector JAR
print(f"Loading connector JAR from: {LIB_DIR}")
env.add_jars(KAFKA_JAR)

# Configure checkpointing for fault tolerance (every 10 seconds)
env.enable_checkpointing(10000)

# =============================================================================
# KAFKA SOURCE
# =============================================================================

kafka_source = (
    KafkaSource.builder()
    .set_bootstrap_servers(KAFKA_BOOTSTRAP_SERVERS)
    .set_topics(KAFKA_TOPIC)
    .set_group_id(KAFKA_GROUP_ID)
    .set_starting_offsets(KafkaOffsetsInitializer.latest())
    .set_value_only_deserializer(SimpleStringSchema())
    .build()
)

# Create data stream from Kafka
stream = env.from_source(
    kafka_source,
    WatermarkStrategy.no_watermarks(),
    "Kafka Source",
)

# =============================================================================
# PROCESS AND WRITE TO CLICKHOUSE
# =============================================================================

# Process each record and write to ClickHouse
clickhouse_sink = ClickHouseSinkFunction(
    host=CLICKHOUSE_HOST,
    port=CLICKHOUSE_PORT,
    database=CLICKHOUSE_DATABASE,
    table=CLICKHOUSE_TABLE,
)
stream.map(clickhouse_sink).print()

# =============================================================================
# EXECUTE
# =============================================================================

print("=" * 60)
print("Flink Streaming Consumer Started!")
print("=" * 60)
print(f"Reading from Kafka: {KAFKA_BOOTSTRAP_SERVERS}/{KAFKA_TOPIC}")
print(f"Writing to ClickHouse: {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DATABASE}.{CLICKHOUSE_TABLE}")
print()
print("Press Ctrl+C to stop.")
print("=" * 60)

# Execute the streaming job
env.execute("Kafka to ClickHouse")
