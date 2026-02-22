"""
Stock Tick Producer

This script generates fake stock price data and sends it to Kafka.
Think of it as simulating a stock market data feed.
"""

import json
import os
import random
import time
from datetime import datetime

from kafka import KafkaProducer

# =============================================================================
# CONFIGURATION
# =============================================================================

# Where Kafka is running
# Use env var for Docker (kafka:29092) or default to localhost for local dev
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# The topic we created earlier
KAFKA_TOPIC = "stock-ticks"

# Stocks we'll generate prices for
STOCKS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]

# Current prices for each stock (will change over time)
current_prices = {
    "AAPL": 150.00,
    "GOOGL": 140.00,
    "MSFT": 380.00,
    "AMZN": 175.00,
    "META": 500.00,
}

# How volatile each tick can be (-10% to +10%)
VOLATILITY = 0.50

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
    Generate a single fake stock tick with volatile price movement.

    Uses a "random walk" - each price changes from the PREVIOUS price,
    creating realistic-looking volatile movements.
    """
    # Pick a random stock
    symbol = random.choice(STOCKS)

    # Get current price and apply random fluctuation (random walk)
    old_price = current_prices[symbol]
    fluctuation = random.uniform(-VOLATILITY, VOLATILITY)
    new_price = round(old_price * (1 + fluctuation), 2)

    # Prevent price from going negative or too low
    new_price = max(new_price, 1.0)

    # Update the current price for next time (random walk)
    current_prices[symbol] = new_price

    # Random volume
    volume = random.randint(100, 10000)

    # Current timestamp
    timestamp = datetime.now().isoformat()

    return {
        "symbol": symbol,
        "price": new_price,
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
