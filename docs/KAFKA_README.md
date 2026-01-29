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

## Topics In-Depth

### What is a Topic?

A **topic** is like a **folder** or **channel** where messages are stored.

```text
Kafka
├── stock-ticks (topic)      <-- we'll create this
│   ├── message 1: "AAPL: $150"
│   ├── message 2: "GOOGL: $140"
│   └── message 3: "MSFT: $380"
│
├── user-signups (topic)     <-- another example
│   ├── message 1: "user123 signed up"
│   └── message 2: "user456 signed up"
│
└── orders (topic)           <-- another example
    └── ...
```

Producers send messages **to a specific topic**. Consumers read **from a specific topic**.

### Create Topic Command

```bash
/opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic stock-ticks \
  --partitions 1 \
  --replication-factor 1
```

Breaking it down:

| Part | Meaning |
| ---- | ------- |
| `/opt/kafka/bin/kafka-topics.sh` | The script to manage topics |
| `--bootstrap-server localhost:9092` | Where Kafka is running |
| `--create` | The action: create a new topic |
| `--topic stock-ticks` | Name of the topic |
| `--partitions 1` | Split into 1 partition (explained below) |
| `--replication-factor 1` | Keep 1 copy (we only have 1 broker) |

### What are Partitions?

A partition splits a topic for **parallelism**:

```text
Without partitions (1 partition):
  stock-ticks
  [msg1] [msg2] [msg3] [msg4] [msg5]
     └──────────────────────────────── 1 consumer reads all

With 3 partitions:
  stock-ticks
  ├── partition 0: [msg1] [msg4]  ─── consumer A
  ├── partition 1: [msg2] [msg5]  ─── consumer B
  └── partition 2: [msg3]         ─── consumer C
                                      (3 consumers read in parallel!)
```

For learning, **1 partition is fine**. In production, more partitions = more throughput.

### Verify Topic Exists

```bash
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### See Topic Details

```bash
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic stock-ticks
```

## Docker Compose Configuration Explained

### Basic Service Setup

```yaml
services:
  kafka:
    image: apache/kafka:3.7.0    # Official Apache Kafka image
    container_name: kafka        # Name for easy reference in logs/commands
```

- We use the official `apache/kafka` image
- `container_name: kafka` lets us run commands like `docker exec kafka ...`

### Port Mapping

```yaml
ports:
  - "9092:9092"  # HOST_PORT:CONTAINER_PORT
```

```text
Your Machine                     Docker Container
+------------------+            +------------------+
|                  |            |                  |
|  Python script   |  ------>   |  Kafka broker    |
|  localhost:9092  |   9092     |  listening :9092 |
|                  |            |                  |
+------------------+            +------------------+
```

Maps container port 9092 to host port 9092, allowing your Python producer to connect to `localhost:9092`.

### KRaft Mode (No Zookeeper)

Before Kafka 3.x, you needed Zookeeper to manage cluster metadata. KRaft (Kafka Raft) lets Kafka manage itself - simpler setup!

```yaml
# Unique ID for this Kafka node (we only have 1 node)
KAFKA_NODE_ID: 1

# This node acts as BOTH controller AND broker:
# - Controller: manages cluster metadata (who's leader, partitions, etc.)
# - Broker: actually stores and serves messages
KAFKA_PROCESS_ROLES: broker,controller

# List of controller nodes that vote on cluster decisions
# Format: NODE_ID@HOST:PORT
KAFKA_CONTROLLER_QUORUM_VOTERS: 1@localhost:9093
```

### Listener Configuration

Listeners define how clients connect to Kafka.

```yaml
# Network interfaces Kafka binds to
# - PLAINTEXT://:9092 = broker listens on port 9092 (for producers/consumers)
# - CONTROLLER://:9093 = internal port for controller communication
KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093

# What address to tell clients to connect to
# Since we're running locally, clients connect to localhost:9092
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092

# Security protocol for each listener (PLAINTEXT = no encryption)
# In production, you'd use SSL or SASL_SSL
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT

# Which listener the controller uses (internal communication)
KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER

# Which listener handles inter-broker communication
KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
```

### Replication Settings (for single-node setup)

```yaml
# Since we only have 1 broker, we set replication factor to 1
# In production with multiple brokers, you'd use 3 for fault tolerance
KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
```

## Commands

### Start Kafka

```bash
docker-compose up -d
```

- `docker-compose up` reads docker-compose.yml and starts all services
- `-d` means "detached" (run in background, don't block your terminal)

### Check Logs

```bash
docker logs kafka
```

- Shows stdout/stderr output from the container named "kafka"
- Add `-f` to follow logs in real-time: `docker logs -f kafka`

### Stop Kafka

```bash
docker-compose down
```

- Stops and removes all containers defined in docker-compose.yml
- Add `-v` to also remove volumes (will delete all Kafka data)

## Understanding `docker exec`

`docker exec` lets you run commands **inside** a running container.

```text
docker exec <container_name> <command>

Example:
docker exec kafka ls /opt/kafka/bin
         |     |   |
         |     |   +-- Command to run inside the container
         |     +------ Container name (from docker-compose.yml)
         +------------ Docker command to execute in container
```

Think of it like SSH-ing into the container and running a command.

## Kafka Directory Structure (inside container)

The `apache/kafka` image organizes files like this:

```text
/opt/kafka/
├── bin/                    # Kafka command-line tools
│   ├── kafka-topics.sh         # Create, list, delete topics
│   ├── kafka-console-producer.sh   # Send messages from terminal
│   ├── kafka-console-consumer.sh   # Read messages from terminal
│   ├── kafka-consumer-groups.sh    # Manage consumer groups
│   └── ...
├── config/                 # Configuration files
│   ├── server.properties       # Main Kafka config
│   └── ...
├── libs/                   # Java JAR files (Kafka is written in Java)
└── logs/                   # Kafka log files
```

## Topic Commands

### List All Topics

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
```

Breaking down the command:

- `docker exec kafka` - run command inside the "kafka" container
- `/opt/kafka/bin/kafka-topics.sh` - path to the topics management script
- `--bootstrap-server localhost:9092` - tell the script where Kafka is running
- `--list` - the action we want (list all topics)

### Create a Topic

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic stock-ticks \
  --partitions 1 \
  --replication-factor 1
```

Breaking down the flags:

- `--create` - we want to create a new topic
- `--topic stock-ticks` - name of the topic
- `--partitions 1` - split topic into 1 partition (more = more parallelism)
- `--replication-factor 1` - keep 1 copy of data (more = more fault tolerance, but we only have 1 broker)

### Describe a Topic (see details)

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic stock-ticks
```

### Delete a Topic

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --topic stock-ticks
```

## Console Consumer (Read Messages)

Use the console consumer to verify messages are being received.

```text
Terminal 1 (producer)          Terminal 2 (consumer)

python producer.py             kafka-console-consumer.sh
    │                              │
    │  sends messages              │  reads messages
    ▼                              ▼
+─────────────────────────────────────+
│            Kafka                    │
│         [stock-ticks]               │
│  msg1, msg2, msg3, msg4 ...         │
+─────────────────────────────────────+
```

### From Outside the Container

```bash
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic stock-ticks \
  --from-beginning
```

### From Inside the Container

If you're already attached to the Kafka container:

```bash
/opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic stock-ticks \
  --from-beginning
```

### Command Breakdown

| Part | Meaning |
| ---- | ------- |
| `kafka-console-consumer.sh` | Built-in script to read messages |
| `--bootstrap-server localhost:9092` | Where Kafka is running |
| `--topic stock-ticks` | Which topic to read from |
| `--from-beginning` | Start from the first message (not just new ones) |

### Other Useful Flags

| Flag | Meaning |
| ---- | ------- |
| `--from-beginning` | Read all messages from start |
| (no flag) | Only read NEW messages arriving after you start |
| `--max-messages 10` | Stop after reading 10 messages |
