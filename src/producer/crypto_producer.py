"""
Real-Time Crypto Producer

Streams real-time cryptocurrency prices from Coinbase WebSocket to Kafka.
No API key required - uses public Coinbase WebSocket API.

Symbols: BTC, ETH, SOL, XRP, DOGE (vs USD)

Usage:
    python src/producer/crypto_producer.py
"""

import json
import signal
import sys
from datetime import datetime, timezone

from kafka import KafkaProducer

# =============================================================================
# CONFIGURATION
# =============================================================================

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
KAFKA_TOPIC = "stock-ticks"  # Reuse same topic for compatibility

# Crypto symbols to track (Coinbase product IDs)
PRODUCTS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]

# Map Coinbase product IDs to display names
SYMBOL_NAMES = {
    "BTC-USD": "BTC",
    "ETH-USD": "ETH",
    "SOL-USD": "SOL",
    "XRP-USD": "XRP",
    "DOGE-USD": "DOGE",
}

# =============================================================================
# KAFKA PRODUCER
# =============================================================================

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

# =============================================================================
# WEBSOCKET HANDLER
# =============================================================================

def on_message(ws, message):
    """Handle incoming WebSocket message."""
    try:
        data = json.loads(message)

        # Only process ticker messages
        if data.get("type") != "ticker":
            return

        product_id = data.get("product_id", "")
        symbol = SYMBOL_NAMES.get(product_id, product_id.replace("-USD", ""))

        price = float(data.get("price", 0))
        volume = int(float(data.get("last_size", 0)) * 1000)  # Scale up for visibility

        if price <= 0:
            return

        # Create tick message
        tick = {
            "symbol": symbol,
            "price": price,
            "volume": max(volume, 1),  # Ensure at least 1
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Send to Kafka
        producer.send(KAFKA_TOPIC, tick)
        print(f"Sent: {tick}")

    except Exception as e:
        print(f"Error processing message: {e}")


def on_error(ws, error):
    """Handle WebSocket error."""
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    """Handle WebSocket close."""
    print(f"WebSocket closed: {close_status_code} - {close_msg}")


def on_open(ws):
    """Handle WebSocket open."""
    print("WebSocket connected to Coinbase")

    # Subscribe to ticker channel for all products
    subscribe_msg = {
        "type": "subscribe",
        "product_ids": PRODUCTS,
        "channels": ["ticker"]
    }
    ws.send(json.dumps(subscribe_msg))
    print(f"Subscribed to: {', '.join(SYMBOL_NAMES.values())}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    import websocket

    print("=" * 60)
    print("Real-Time Crypto Producer (Coinbase WebSocket)")
    print("=" * 60)
    print(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS}/{KAFKA_TOPIC}")
    print(f"Symbols: {', '.join(SYMBOL_NAMES.values())}")
    print()
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    # Coinbase WebSocket URL
    ws_url = "wss://ws-feed.exchange.coinbase.com"

    # Create WebSocket connection
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nShutting down...")
        ws.close()
        producer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run WebSocket (blocks until closed)
    ws.run_forever()


if __name__ == "__main__":
    main()
