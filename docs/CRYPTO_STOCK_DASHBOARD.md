# Crypto Dashboard Documentation

The crypto dashboard displays **real-time cryptocurrency prices** from Coinbase via WebSocket.

## Architecture

```text
┌─────────────────┐    ┌─────────────┐    ┌─────────┐    ┌──────────┐    ┌────────────┐
│    Coinbase     │───▶│   Crypto    │───▶│  Kafka  │───▶│ Consumer │───▶│ ClickHouse │
│ WebSocket API   │    │  Producer   │    │         │    │          │    │            │
│ (Real trades)   │    │  (Python)   │    │         │    │          │    │            │
└─────────────────┘    └─────────────┘    └─────────┘    └──────────┘    └────────────┘
        │                                                                      │
   Real market                                                                 ▼
   data 24/7                                                              Dashboard
```

## Data Source: Coinbase WebSocket

The crypto producer connects to Coinbase's public WebSocket API to receive real-time trade data.

### Connection Details

| Property | Value |
|----------|-------|
| WebSocket URL | `wss://ws-feed.exchange.coinbase.com` |
| API Key Required | No (public endpoint) |
| Authentication | None |
| Data Type | Real trades as they happen |
| Availability | 24/7 (crypto markets never close) |

### Subscribed Products

| Product ID | Display Symbol | Description |
|------------|----------------|-------------|
| BTC-USD | BTC | Bitcoin |
| ETH-USD | ETH | Ethereum |
| SOL-USD | SOL | Solana |
| XRP-USD | XRP | Ripple |
| DOGE-USD | DOGE | Dogecoin |

## How It Works

### 1. Crypto Producer (`src/producer/crypto_producer.py`)

Connects to Coinbase WebSocket and forwards trades to Kafka:

```python
# WebSocket URL
ws_url = "wss://ws-feed.exchange.coinbase.com"

# Subscribe to ticker channel for live trades
subscribe_msg = {
    "type": "subscribe",
    "product_ids": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"],
    "channels": ["ticker"]
}

# When a trade happens on Coinbase:
def on_message(ws, message):
    data = json.loads(message)
    # Example: {"type": "ticker", "product_id": "BTC-USD", "price": "77302.99", ...}

    tick = {
        "symbol": "BTC",
        "price": 77302.99,  # Real market price
        "volume": 45,
        "timestamp": "2026-01-31T18:41:18+00:00"
    }
    producer.send("stock-ticks", tick)
```

### 2. Data Flow

```text
1. Someone buys/sells BTC on Coinbase exchange
           ↓
2. Coinbase broadcasts the trade via WebSocket
           ↓
3. crypto_producer.py receives: {"price": "77302.99", "product_id": "BTC-USD"}
           ↓
4. Transforms and sends to Kafka: {"symbol": "BTC", "price": 77302.99, ...}
           ↓
5. Consumer (Spark/Flink) reads from Kafka and writes to ClickHouse
           ↓
6. Dashboard queries API: /api/latest?symbols=BTC,ETH,SOL,XRP,DOGE
           ↓
7. Browser displays real prices with auto-refresh
```

### 3. Dashboard Frontend (`src/dashboard/static/crypto_index.html`)

The frontend filters for crypto symbols only:

```javascript
// Only show crypto symbols
const SYMBOLS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'];
const SYMBOLS_PARAM = SYMBOLS.join(',');

// Fetch only crypto data
const latest = await fetch(`/api/latest?symbols=${SYMBOLS_PARAM}`);
```

## Comparison: Stock vs Crypto Dashboard

| Component | Stock Dashboard | Crypto Dashboard |
|-----------|-----------------|------------------|
| **Producer** | `stock_producer.py` (synthetic) | `crypto_producer.py` (Coinbase) |
| **Data Source** | Random generated | Real Coinbase trades |
| **Symbols** | AAPL, AMZN, GOOGL, META, MSFT | BTC, ETH, SOL, XRP, DOGE |
| **Kafka Topic** | `stock-ticks` | `stock-ticks` (same) |
| **Consumer** | Spark or Flink | Spark or Flink (same) |
| **ClickHouse Table** | `ticks` | `ticks` (same) |
| **Dashboard File** | `stock_index.html` | `crypto_index.html` |
| **Default Refresh** | 5 seconds | 2 seconds |
| **Availability** | When producer runs | 24/7 (real market) |

## Why Coinbase?

| Exchange | API Key Required | Globally Available | Notes |
|----------|------------------|-------------------|-------|
| Binance | No | No (blocked in some regions) | HTTP 451 error |
| **Coinbase** | **No** | **Yes** | Best option |
| Kraken | No | Yes | Lower volume |

Coinbase was chosen because:

- **Free** - No API key or account required
- **Public** - Just connect and subscribe
- **Real-time** - Actual trades as they execute
- **Reliable** - Available globally
- **High volume** - Popular exchange with frequent trades

## Usage

### Run with Crypto Data

```bash
# Using run.sh
./run.sh --crypto                # Spark + Streamlit + Crypto
./run.sh flink web --crypto      # Flink + Web Dashboard + Crypto

# Or run producer directly
python src/producer/crypto_producer.py
```

### Dashboard URLs

| Dashboard | URL |
|-----------|-----|
| Streamlit | <http://localhost:8501> |
| Web (FastAPI) | <http://localhost:8502> |

## Files

| File | Purpose |
|------|---------|
| `src/producer/crypto_producer.py` | Coinbase WebSocket → Kafka |
| `src/dashboard/static/crypto_index.html` | Crypto dashboard UI |
| `src/dashboard/web_app.py` | API server (serves crypto UI with `--crypto` flag) |

## Troubleshooting

### No data showing

- Ensure Kafka and ClickHouse are running: `docker compose up -d`
- Check crypto producer is connected: Look for "WebSocket connected to Coinbase"
- Verify consumer is running and writing to ClickHouse

### Mixed stock/crypto data

- The dashboards filter by symbol, but old data may exist in ClickHouse
- Clear the table if needed: `docker exec clickhouse clickhouse-client -q "TRUNCATE TABLE stocks.ticks"`

### WebSocket disconnects

- Coinbase may disconnect idle connections
- The producer will show "WebSocket closed" - restart it if needed
