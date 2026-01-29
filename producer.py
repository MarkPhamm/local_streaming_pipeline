"""
Stock Tick Producer

This script generates fake stock price data and sends it to Kafka.
Think of it as simulating a stock market data feed.
"""

import json
import random
import time
from datetime import datetime

from kafka import KafkaProducer

# =============================================================================
# CONFIGURATION
# =============================================================================

# Where Kafka is running (our Docker container exposes port 9092)
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

# The topic we created earlier
KAFKA_TOPIC = "stock-ticks"

# Stocks we'll generate prices for
STOCKS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]

# Starting prices for each stock (we'll fluctuate around these)
BASE_PRICES = {
    "AAPL": 150.00,
    "GOOGL": 140.00,
    "MSFT": 380.00,
    "AMZN": 175.00,
    "META": 500.00,
}

# =============================================================================
# CREATE THE PRODUCER
# =============================================================================
# KafkaProducer is the main class for sending messages
# - bootstrap_servers: list of Kafka brokers to connect to
# - value_serializer: how to convert Python objects to bytes
#   (Kafka only understands bytes, so we convert dict -> JSON string -> bytes)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

# =============================================================================
# GENERATE STOCK TICK DATA
# =============================================================================
def generate_stock_tick():
    """
    Generate a single fake stock tick.

    Returns a dict like:
    {
        "symbol": "AAPL",
        "price": 150.25,
        "volume": 1523,
        "timestamp": "2026-01-29T10:30:00.123456"
    }
    """
    # Pick a random stock
    symbol = random.choice(STOCKS)

    # Get base price and add some random fluctuation (-2% to +2%)
    base_price = BASE_PRICES[symbol]
    fluctuation = random.uniform(-0.02, 0.02)  # -2% to +2%
    price = round(base_price * (1 + fluctuation), 2)

    # Random volume (number of shares traded)
    volume = random.randint(100, 10000)

    # Current timestamp
    timestamp = datetime.now().isoformat()

    return {
        "symbol": symbol,
        "price": price,
        "volume": volume,
        "timestamp": timestamp,
    }


# =============================================================================
# MAIN LOOP - SEND MESSAGES TO KAFKA
# =============================================================================

if __name__ == "__main__":
    print("Starting producer...")
    print(f"Sending to topic: {KAFKA_TOPIC}")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            # Generate a stock tick
            tick = generate_stock_tick()

            # Send to Kafka
            # - topic: which topic to send to
            # - value: the message (will be serialized by value_serializer)
            producer.send(KAFKA_TOPIC, value=tick)

            # Print what we sent (so we can see it working)
            print(f"Sent: {tick}")

            # Wait 1 second before sending the next tick
            time.sleep(1)

    except KeyboardInterrupt:
        # User pressed Ctrl+C
        print("\nStopping producer...")

    finally:
        # Always close the producer to flush any remaining messages
        producer.close()
        print("Producer closed.")
