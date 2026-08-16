# ADR-004: Kafka Data Pipeline

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

The Insider Threat system must ingest activity data from numerous external sources (Windows Event Logs, Linux Audit Logs, Application Logs, Database Logs, EDR/XDR, DLP, Firewall/Proxy, WAF, Email Security, Microsoft 365, Slack/Teams, VPN Logs, DNS Logs, NetFlow/IPFIX, IOC Feeds, Threat Feeds) and process it through a multi-stage pipeline before it reaches the Activity Collection Service.

The required pipeline stages are:

```
External Log Sources → Collectors → Message Queue → Stream Processing
→ Normalization & Enrichment → Feature Extraction → Feature Store → Activity Collection Service
```

**Key tensions:**
- Log sources produce data at varying rates — network logs (NetFlow/IPFIX) can generate millions of events per second; application logs may produce hundreds per minute.
- The pipeline must guarantee **no data loss** — missed security events could mean missed insider threats.
- Processing stages (normalization, enrichment, feature extraction) need to be independently scalable.
- Downstream services (Activity Collection, Behavioral Profiling, Anomaly Detection) consume at different rates and cannot be back-pressured by ingestion volume.
- The system must support **event replay** for forensic investigation — an analyst may need to reprocess events from a specific time window.

## Decision

Adopt **Apache Kafka** as the central message broker for the Data Processing & Streaming Layer.

### Pipeline Architecture

```
External Sources → Collectors/Connectors
                        ↓
              Kafka Topic: raw-events
                        ↓
              Stream Processing (Faust/kafka-python)
                        ↓
              Kafka Topic: normalized-events
                        ↓
              Enrichment Consumers
                        ↓
              Kafka Topic: enriched-events
                        ↓
              Feature Extraction Consumers
                        ↓
              Redis Feature Store + Kafka Topic: processed-events
                        ↓
              Activity Collection Service (consumer)
```

### Kafka Topic Design

| Topic | Purpose | Retention | Partitions |
|-------|---------|-----------|-----------|
| `raw-events` | Unprocessed events from collectors | 7 days | By source type |
| `normalized-events` | Schema-normalized events | 3 days | By user ID |
| `enriched-events` | Events with identity/geo/context enrichment | 3 days | By user ID |
| `processed-events` | Fully processed, feature-extracted events | 14 days | By user ID |
| `domain-events` | Inter-module domain events (alerts, risk changes) | 3 days | By event type |
| `dead-letter` | Failed processing attempts for manual review | 30 days | Single |

### Why Kafka (Not RabbitMQ for the Pipeline)

| Capability | Kafka | RabbitMQ |
|-----------|-------|---------|
| **Event replay** | ✅ Consumer offsets allow replaying from any point | ❌ Messages deleted after acknowledgment |
| **Ordering guarantees** | ✅ Per-partition ordering | ⚠️ Per-queue, no partitioning |
| **Throughput** | ✅ Millions of events/second | ⚠️ Tens of thousands/second |
| **Backpressure handling** | ✅ Consumers pull at their own rate | ⚠️ Push-based, requires flow control |
| **Stream processing** | ✅ Native Kafka Streams / Faust integration | ❌ Requires separate stream processor |
| **Durability** | ✅ Replicated, configurable retention | ✅ Durable queues |
| **Multi-consumer** | ✅ Consumer groups, independent consumption | ⚠️ Competing consumers only |

### Implementation Approach

- **Python Kafka client**: `aiokafka` for async FastAPI-compatible producers/consumers
- **Stream processing**: `Faust` (Python stream processing library built on Kafka) for lightweight stream processing within the monolith; upgrade to Spark Streaming / Flink when scale demands
- **Schema management**: JSON Schema registry for event schema evolution (Confluent Schema Registry or custom)
- **Consumer groups**: Each pipeline stage and each downstream service module runs its own consumer group, enabling independent scaling and replay

## Consequences

### Positive
- **No data loss**: Kafka's replicated commit log ensures events survive broker failures. Events are retained for configurable periods, enabling replay.
- **Event replay for forensics**: Investigators can reprocess events from a specific time window by resetting consumer offsets — critical for insider threat investigation.
- **Independent scaling**: Each pipeline stage (normalization, enrichment, feature extraction) can scale independently by adding consumers to the consumer group.
- **Decoupled pipeline stages**: Each stage reads from one topic and writes to another. A stage can be updated, restarted, or replaced without affecting others.
- **Activity Collection as pure consumer**: The Activity Collection Service reads from `processed-events` topic. It doesn't need to know about collectors, normalization, or enrichment — it just receives clean, processed events.
- **Multi-consumer support**: The same event can be consumed by Activity Collection (for persistence), Anomaly Detection (for real-time analysis), and Reporting (for metrics) simultaneously via separate consumer groups.

### Negative
- **Operational complexity**: Kafka requires ZooKeeper (or KRaft in newer versions), broker management, topic configuration, partition rebalancing. Significantly more complex to operate than RabbitMQ.
- **Development environment overhead**: Running Kafka in Docker for local development requires more resources (~1-2GB RAM for Kafka + ZooKeeper).
- **Learning curve**: Kafka's concepts (partitions, consumer groups, offsets, rebalancing) require dedicated learning.
- **Message size limits**: Kafka is optimized for small messages (< 1MB). Large payloads (file attachments, screenshots) must go through Object Storage with only references in Kafka.
- **Eventual consistency**: Events flowing through the pipeline introduce latency between data generation and availability in the Activity Collection Service. Typical latency: sub-second to a few seconds.

## Alternatives Considered

### 1. RabbitMQ Only
- **Pros**: Simpler to operate, excellent for task routing and request-reply patterns, lower resource requirements, built-in management UI.
- **Cons**: No event replay (messages are deleted after acknowledgment). Limited throughput for high-volume log ingestion. Push-based model can overwhelm slow consumers. No native stream processing integration.
- **Rejected for the pipeline because**: Event replay is a hard requirement for forensic investigation. However, RabbitMQ may still be used for inter-module command/task routing (e.g., "generate report", "send notification") if Celery is needed alongside Kafka.

### 2. Redis Streams
- **Pros**: Already in the stack (Redis is used for caching). Simpler than Kafka. Consumer groups supported.
- **Cons**: Persistence is best-effort (RDB/AOF), not designed for durable event storage. No built-in partitioning across nodes (requires Redis Cluster). Limited retention management. No ecosystem for stream processing.
- **Rejected because**: Redis Streams lack the durability guarantees and ecosystem maturity needed for a security-critical data pipeline where no event can be lost.

### 3. AWS Kinesis / GCP Pub/Sub / Azure Event Hubs
- **Pros**: Fully managed, auto-scaling, no operational overhead.
- **Cons**: Cloud vendor lock-in. Not available for on-premise deployments. Cost scales linearly with throughput. Harder to develop against locally.
- **Rejected because**: The system must support on-premise deployment (enterprise customers with data sovereignty requirements). Kafka can run anywhere — on-premise, in containers, or as a managed service (Confluent, AWS MSK).

### 4. Direct Database Writes (No Message Queue)
- **Pros**: Simplest architecture. Collectors write directly to MongoDB.
- **Cons**: No buffering during traffic spikes. No processing pipeline. No replay. Tight coupling between collectors and storage. A database outage would cause data loss.
- **Rejected because**: The multi-stage processing pipeline (normalization → enrichment → feature extraction) requires decoupled, ordered, replayable event transport that only a message broker provides.
