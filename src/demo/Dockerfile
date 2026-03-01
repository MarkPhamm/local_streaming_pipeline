# Builds: stock-producer (profile: stock)
# Synthetic stock data producer that sends fake ticks to Kafka
FROM python:3.12-slim

# Set /app as the working directory for all subsequent commands
WORKDIR /app

# Install Kafka client library for producing messages to Kafka
RUN pip install --no-cache-dir kafka-python-ng==2.2.2

# Copy the producer script into the container
COPY stock_producer_demo.py ./

# Run the producer script on container start
CMD ["python", "stock_producer_demo.py"]
