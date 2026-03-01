FROM python:3.12-slim

WORKDIR /app

# Install dashboard dependencies
RUN pip install --no-cache-dir \
    streamlit \
    streamlit-autorefresh \
    fastapi \
    uvicorn \
    clickhouse-connect

# Copy dashboard files
COPY app.py web_app.py ./
COPY static/ static/

# Default: run Streamlit dashboard
CMD ["streamlit", "run", "app.py", "--server.headless", "true", "--server.port", "8501", "--server.address", "0.0.0.0"]
