FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir kafka-python-ng==2.2.2

COPY stock_producer_demo.py ./

CMD ["python", "stock_producer_demo.py"]
