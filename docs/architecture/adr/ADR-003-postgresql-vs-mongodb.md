# ADR-003: PostgreSQL vs MongoDB (Polyglot Persistence)

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

The system handles fundamentally different categories of data with different access patterns, consistency requirements, and volume characteristics:

1. **Relational/Transactional Data** — Users, roles, permissions, employee profiles, departments, assets, devices, incidents, policies, configurations, playbooks, report definitions, scheduled reports. These require referential integrity, complex joins, ACID transactions, and structured queries.

2. **High-Volume Event Data** — Activity logs, enriched events, case notes, raw incident data. These are append-heavy, schema-flexible, potentially millions of records per day, and rarely updated after creation. They benefit from document-oriented storage with flexible schemas to accommodate diverse log source formats.

**Key tensions:**
- A single database (PostgreSQL only) would simplify operations but force us to store semi-structured event data in JSONB columns, losing MongoDB's native document querying, aggregation pipeline, and horizontal scaling capabilities.
- A single database (MongoDB only) would struggle with the relational data's need for referential integrity, complex multi-table joins, and ACID transactions across related entities.
- Using both databases adds operational complexity (two backup strategies, two monitoring setups, two sets of expertise required).

## Decision

Adopt a **polyglot persistence** strategy:

### PostgreSQL (Primary Relational Store)
**What it stores**: Users, Profiles, Incidents, Policies, Configurations, Roles, Permissions, Assets, Departments, Devices, Playbooks, Workflows, Report Definitions, Scheduled Reports, Notification Preferences, Alert Rules, Risk Score Records.

**Why PostgreSQL**:
- ACID transactions for critical operations (user creation + role assignment must be atomic)
- Referential integrity (employee → department → assets relationships)
- Complex analytical queries with window functions, CTEs, and aggregations
- Mature ecosystem with SQLAlchemy async support (asyncpg driver)
- TimescaleDB extension for time-series analytics (Data Warehouse role)
- Row-level security for multi-tenant isolation (future)

### MongoDB (Document Store)
**What it stores**: Activity Logs, Alerts (raw event data), Incident Data (enriched), Case Notes, Enriched Events from the data pipeline.

**Why MongoDB**:
- Schema flexibility for diverse log sources (Windows Event Logs, Linux Audit, VPN, DNS, EDR — all have different structures)
- Append-heavy write pattern with rare updates
- Native document aggregation pipeline for event analytics
- Horizontal scaling via sharding when activity volume grows
- TTL indexes for automatic data retention management
- Motor async driver for non-blocking I/O with FastAPI

### Data Store Assignment by Module

| Module | PostgreSQL | MongoDB |
|--------|-----------|---------|
| Identity & Access | ✅ Users, Roles, Permissions | — |
| User & Asset Management | ✅ Employees, Departments, Assets, Devices | — |
| Activity Collection | ✅ Log Source config | ✅ Activity events, enriched events |
| Behavioral Profiling | ✅ Baselines, patterns | — |
| Anomaly Detection | ✅ Anomaly records | — |
| Risk Scoring | ✅ Risk scores, trends | — |
| UEBA Intelligence | ✅ Models, predictions | — |
| Threat Investigation | ✅ Incidents, timelines | ✅ Case notes, incident data |
| Alert Management | ✅ Alert rules, routing | ✅ Alert event data |
| Response & Workflow | ✅ Playbooks, workflows | — |
| Reporting & Analytics | ✅ Report defs, schedules | — |
| Notification | ✅ Preferences, records | — |

## Consequences

### Positive
- **Right tool for the job**: Relational data gets ACID guarantees; event data gets schema flexibility and horizontal scaling.
- **Independent scaling**: MongoDB can be sharded independently when activity volume grows, without affecting PostgreSQL's transactional workloads.
- **Schema evolution**: New log source formats can be ingested without database migrations — MongoDB documents accommodate new fields naturally.
- **Retention management**: MongoDB TTL indexes automatically expire old activity data per configured retention policies.
- **Future-proof**: If activity volume exceeds MongoDB's capacity, the document repository interface can be re-implemented against a data lake without changing the domain layer.

### Negative
- **Operational complexity**: Two database systems to provision, monitor, back up, and maintain. Requires expertise in both.
- **No cross-store joins**: Cannot join PostgreSQL users with MongoDB activity logs in a single query. The application layer must perform this correlation.
- **No cross-store transactions**: Creating an alert (PostgreSQL) and storing its raw event data (MongoDB) cannot be an atomic transaction. Mitigated by eventual consistency and the event bus.
- **Increased testing complexity**: Integration tests must spin up both PostgreSQL and MongoDB (Testcontainers).
- **Data consistency gap**: If the PostgreSQL write succeeds but the MongoDB write fails (or vice versa), the system enters an inconsistent state. Mitigated by retry mechanisms and idempotent writes.

## Alternatives Considered

### 1. PostgreSQL Only (with JSONB for Events)
- **Pros**: Single database, simpler operations, JSONB supports flexible schemas, GIN indexes for JSON querying.
- **Cons**: JSONB performance degrades at high volume compared to MongoDB's native document storage. No native sharding. Complex aggregation on JSONB is verbose compared to MongoDB's aggregation pipeline. Mixing high-volume append workloads with transactional CRUD in the same instance creates resource contention.
- **Rejected because**: At scale (millions of events/day), PostgreSQL JSONB cannot match MongoDB's write throughput, aggregation pipeline, or horizontal scaling. However, for teams preferring simplicity, PostgreSQL JSONB is a viable interim step — the Repository Pattern allows migration later.

### 2. MongoDB Only
- **Pros**: Single database technology, flexible schemas everywhere.
- **Cons**: No referential integrity for user → role → permission relationships. Multi-document transactions are possible but slower and less mature than PostgreSQL. Complex analytical queries (window functions, CTEs) are not supported. Not ideal for highly relational configuration data.
- **Rejected because**: The Identity, User Management, and Investigation modules have deeply relational data that benefits from PostgreSQL's strengths.

### 3. PostgreSQL + Apache Cassandra
- **Pros**: Cassandra excels at high-volume write throughput and horizontal scaling.
- **Cons**: Cassandra's query model is table-per-query (no ad-hoc querying), requires careful data modeling upfront, and has a steep learning curve. The team's expertise is in document databases.
- **Rejected because**: MongoDB provides sufficient write throughput for our projected scale while offering a more flexible query model and lower operational complexity.
