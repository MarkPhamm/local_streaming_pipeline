FROM python:3.12-slim

WORKDIR /app

# Install only producer dependencies
RUN pip install --no-cache-dir kafka-python-ng==2.2.2 websocket-client==1.8.0

COPY stock_producer.py crypto_producer.py ./

# Default: run synthetic stock producer
CMD ["python", "stock_producer.py"]
