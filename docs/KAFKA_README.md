# Kafka Setup Guide

## What is Kafka?

Apache Kafka is a **distributed message broker** - think of it as a post office for your data.

### The Problem Kafka Solves

Imagine you have multiple applications that need to share data:

```text
Without Kafka (messy):                With Kafka (clean):

  App A -----> App B                    App A ---\
    |   \                                         \
    |    \---> App C                   App B -----> KAFKA -----> App D
    |                                             /
    v                                  App C ---/              -> App E
  App D -----> App E
```

Without Kafka, every app needs to know about every other app. With Kafka, apps just send messages to Kafka (producers) or read from Kafka (consumers). They don't need to know about each other.

### How It Works (Simple Version)

1. **Producers** send messages to Kafka (e.g., "user clicked button")
2. **Kafka** stores these messages in **topics** (like folders/categories)
3. **Consumers** read messages from topics they care about

```text
Producer                    Kafka                     Consumer
(your app)                (message broker)           (another app)

  "AAPL: $150"  ------>   [stock-ticks topic]  ------>  Read & process
  "GOOGL: $140" ------>   [    message 1     ]  ------>  stock prices
  "MSFT: $380"  ------>   [    message 2     ]
                          [    message 3     ]
```

### Why Kafka?

| Feature | Benefit |
| ------- | ------- |
| **Durable** | Messages are saved to disk, won't lose data if consumer crashes |
| **Scalable** | Can handle millions of messages per second |
| **Decoupled** | Producers and consumers don't need to run at the same time |
| **Replayable** | Consumers can re-read old messages (unlike traditional queues) |

## Architecture Overview

```text
+---------------------------------------------------+
|                 Docker Container                  |
|  +---------------------------------------------+  |
|  |               Kafka (KRaft)                 |  |
|  |                                             |  |
|  |   +-------------+      +--------------+     |  |
|  |   |   Broker    |      |  Controller  |     |  |
|  |   | (port 9092) |      | (port 9093)  |     |  |
|  |   +-------------+      +--------------+     |  |
|  |                                             |  |
|  +---------------------------------------------+  |
|                        |                          |
+------------------------|--------------------------+
                         | port 9092
                         v
                Your Python Producer
             (connects to localhost:9092)
```

## Key Concepts

| Term | Description |
| ---- | ----------- |
| **Broker** | Stores messages, serves producers/consumers |
| **Controller** | Manages cluster state (which broker has which partition) |
| **Zookeeper** | A separate service that older Kafka versions used to store cluster metadata (topic configs, broker list, partition leaders). Acts as a centralized coordination service. Kafka 3.x+ replaced this with KRaft |
| **KRaft** | Kafka Raft - Kafka managing itself without Zookeeper. The controller role is built into Kafka itself, using the Raft consensus protocol |
| **Listener** | A network endpoint where Kafka accepts connections |
| **Topic** | A category/feed name to which messages are published |
| **Partition** | A topic is split into partitions for parallelism |

## Docker Compose Configuration Explained

### Basic Service Setup

```yaml
version: '3.8'  # Docker Compose file format version

services:
  kafka:
    image: bitnami/kafka:latest  # Well-maintained Kafka image
    container_name: kafka        # Name for easy reference in logs/commands
```

### Port Mapping

```yaml
ports:
  - "9092:9092"  # HOST_PORT:CONTAINER_PORT
```

Maps container port 9092 to host port 9092, allowing your Python producer to connect to `localhost:9092`.

### KRaft Mode (No Zookeeper)

Before Kafka 3.x, you needed Zookeeper to manage cluster metadata. KRaft (Kafka Raft) lets Kafka manage itself - simpler setup!

```yaml
# Unique ID for this Kafka node (we only have 1 node, so it's 0)
KAFKA_CFG_NODE_ID=0

# This node acts as BOTH controller AND broker:
# - Controller: manages cluster metadata (who's leader, partitions, etc.)
# - Broker: actually stores and serves messages
KAFKA_CFG_PROCESS_ROLES=controller,broker

# List of controller nodes that vote on cluster decisions
# Format: NODE_ID@HOST:PORT
KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=0@kafka:9093
```

### Listener Configuration

Listeners define how clients connect to Kafka.

```yaml
# Network interfaces Kafka binds to
# - PLAINTEXT://:9092 = broker listens on port 9092 (for producers/consumers)
# - CONTROLLER://:9093 = internal port for controller communication
KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093

# What address to tell clients to connect to
# Since we're running locally, clients connect to localhost:9092
KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092

# Security protocol for each listener (PLAINTEXT = no encryption)
# In production, you'd use SSL or SASL_SSL
KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT

# Which listener the controller uses (internal communication)
KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER
```

### Topic Configuration

```yaml
# Auto-create topics when a producer first sends to them
# Convenient for development (in production, you'd create topics explicitly)
KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE=true
```

## Commands

### Start Kafka

```bash
docker-compose up -d
```

### Check Logs

```bash
docker logs kafka
```

### Stop Kafka

```bash
docker-compose down
```

### List Topics

```bash
docker exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### Create a Topic Manually

```bash
docker exec kafka kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic stock-ticks --partitions 1 --replication-factor 1
```
