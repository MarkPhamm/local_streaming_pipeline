"""
Stock/Crypto Dashboard - Web API

A simple FastAPI backend that serves the dashboard
and provides API endpoints for ClickHouse data.

Run with:
    uvicorn src.dashboard.web_app:app --reload --port 8502

Or:
    python src/dashboard/web_app.py
    python src/dashboard/web_app.py --crypto   # Crypto dashboard
"""

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager

import clickhouse_connect
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--crypto", action="store_true", help="Use crypto dashboard")
parser.add_argument("--port", type=int, default=8502, help="Port to run on")
args, _ = parser.parse_known_args()

# Dashboard mode
DASHBOARD_MODE = "crypto" if args.crypto else "stock"

# =============================================================================
# CLICKHOUSE CONNECTION
# =============================================================================

client = None


def get_client():
    """Get or create ClickHouse client."""
    global client
    if client is None:
        client = clickhouse_connect.get_client(
            host="localhost",
            port=8123,
            database="stocks",
        )
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: initialize client
    get_client()
    yield
    # Shutdown: close client
    global client
    if client:
        client.close()


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Stock Ticks Dashboard API",
    lifespan=lifespan,
)

# Get the directory where this file is located
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(DASHBOARD_DIR, "static")

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# =============================================================================
# API ENDPOINTS
# =============================================================================


@app.get("/")
async def root():
    """Serve the main dashboard page based on mode."""
    if DASHBOARD_MODE == "crypto":
        return FileResponse(os.path.join(STATIC_DIR, "crypto_index.html"))
    return FileResponse(os.path.join(STATIC_DIR, "stock_index.html"))


@app.get("/api/latest")
async def get_latest_prices(symbols: str = ""):
    """Get latest price for each symbol."""
    symbol_filter = ""
    if symbols:
        symbol_list = ", ".join([f"'{s}'" for s in symbols.split(",")])
        symbol_filter = f"WHERE symbol IN ({symbol_list})"

    query = f"""
    SELECT
        symbol,
        argMax(price, timestamp) as price,
        argMax(volume, timestamp) as volume,
        max(timestamp) as last_update
    FROM ticks
    {symbol_filter}
    GROUP BY symbol
    ORDER BY symbol
    """
    result = get_client().query(query)
    return [
        {
            "symbol": row[0],
            "price": row[1],
            "volume": row[2],
            "last_update": str(row[3]),
        }
        for row in result.result_rows
    ]


@app.get("/api/history")
async def get_price_history(symbols: str = "", minutes: int = 60):
    """Get price history for selected symbols."""
    symbol_list = symbols.split(",") if symbols else []

    if not symbol_list:
        return []

    symbols_str = ", ".join([f"'{s}'" for s in symbol_list])
    time_filter = f"AND timestamp > now() - INTERVAL {minutes} MINUTE" if minutes > 0 else ""

    query = f"""
    SELECT
        timestamp,
        symbol,
        price
    FROM ticks
    WHERE symbol IN ({symbols_str})
      {time_filter}
    ORDER BY timestamp
    """
    result = get_client().query(query)
    return [
        {
            "timestamp": str(row[0]),
            "symbol": row[1],
            "price": row[2],
        }
        for row in result.result_rows
    ]


@app.get("/api/recent")
async def get_recent_ticks(symbols: str = "", limit: int = 20):
    """Get most recent ticks."""
    symbol_filter = ""
    if symbols:
        symbol_list = ", ".join([f"'{s}'" for s in symbols.split(",")])
        symbol_filter = f"WHERE symbol IN ({symbol_list})"

    query = f"""
    SELECT
        timestamp,
        symbol,
        price,
        volume
    FROM ticks
    {symbol_filter}
    ORDER BY timestamp DESC
    LIMIT {limit}
    """
    result = get_client().query(query)
    return [
        {
            "timestamp": str(row[0]),
            "symbol": row[1],
            "price": row[2],
            "volume": row[3],
        }
        for row in result.result_rows
    ]


@app.get("/api/stats")
async def get_stats(symbols: str = ""):
    """Get price statistics by symbol."""
    symbol_filter = ""
    if symbols:
        symbol_list = ", ".join([f"'{s}'" for s in symbols.split(",")])
        symbol_filter = f"WHERE symbol IN ({symbol_list})"

    query = f"""
    SELECT
        symbol,
        count() as tick_count,
        round(min(price), 2) as min_price,
        round(max(price), 2) as max_price,
        round(avg(price), 2) as avg_price,
        sum(volume) as total_volume
    FROM ticks
    {symbol_filter}
    GROUP BY symbol
    ORDER BY symbol
    """
    result = get_client().query(query)
    return [
        {
            "symbol": row[0],
            "tick_count": row[1],
            "min_price": row[2],
            "max_price": row[3],
            "avg_price": row[4],
            "total_volume": row[5],
        }
        for row in result.result_rows
    ]


@app.get("/api/count")
async def get_total_count(symbols: str = ""):
    """Get total tick count."""
    symbol_filter = ""
    if symbols:
        symbol_list = ", ".join([f"'{s}'" for s in symbols.split(",")])
        symbol_filter = f"WHERE symbol IN ({symbol_list})"

    result = get_client().query(f"SELECT count() FROM ticks {symbol_filter}")
    return {"count": result.result_rows[0][0]}


@app.get("/api/symbols")
async def get_symbols():
    """Get list of all symbols."""
    result = get_client().query("SELECT DISTINCT symbol FROM ticks ORDER BY symbol")
    return [row[0] for row in result.result_rows]


# =============================================================================
# SSE - Real-time Stream
# =============================================================================

last_seen_timestamp = {}


@app.get("/api/stream")
async def stream_ticks(symbols: str = ""):
    """Stream new ticks via Server-Sent Events."""

    async def event_generator():
        last_ts = None
        while True:
            try:
                symbol_filter = ""
                if symbols:
                    symbol_list = ", ".join([f"'{s}'" for s in symbols.split(",")])
                    symbol_filter = f"AND symbol IN ({symbol_list})"

                ts_filter = ""
                if last_ts:
                    ts_filter = f"AND timestamp > '{last_ts}'"

                query = f"""
                SELECT timestamp, symbol, price, volume
                FROM ticks
                WHERE 1=1 {symbol_filter} {ts_filter}
                ORDER BY timestamp DESC
                LIMIT 50
                """
                result = get_client().query(query)
                rows = result.result_rows

                if rows:
                    last_ts = str(rows[0][0])
                    ticks = [
                        {
                            "timestamp": str(r[0]),
                            "symbol": r[1],
                            "price": r[2],
                            "volume": r[3],
                        }
                        for r in reversed(rows)
                    ]
                    yield f"data: {json.dumps(ticks)}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)
