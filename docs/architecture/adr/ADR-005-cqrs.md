# ADR-005: CQRS (Command Query Responsibility Segregation)

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

The Insider Threat system has dramatically different read and write characteristics:

**Write side (Commands):**
- Activity event ingestion: high volume, append-only, write-optimized
- Alert generation: triggered by anomaly detection, requires domain validation
- Investigation creation: complex multi-step workflow with evidence attachment
- Risk score updates: batch recalculation with domain logic

**Read side (Queries):**
- SOC Analyst dashboards: aggregate risk scores, alert counts, trend charts — read-heavy, tolerance for slight staleness
- Activity search: full-text search across millions of events with filters, pagination, sorting
- Investigation timeline: chronological reconstruction from multiple data sources
- Reporting: complex analytical queries with aggregations, grouping, and window functions

**Key tensions:**
- Optimizing data models for writes (normalized, event-sourced) conflicts with optimizing for reads (denormalized, pre-aggregated).
- Dashboard queries touching PostgreSQL's transactional tables during heavy write periods cause lock contention and degrade both read and write performance.
- Some queries span multiple data stores (join PostgreSQL user data with MongoDB activity data with Elasticsearch alert data), which is impossible in a single SQL query.

## Decision

Adopt **CQRS at the application layer** within the modular monolith. Commands and Queries are separate use case classes with different data access paths.

### Implementation Strategy

```
Commands (Writes)                          Queries (Reads)
─────────────────                          ───────────────
CommandRouter → UseCase → Domain Entity    QueryRouter → QueryHandler → Read Model
                  ↓                                            ↓
           Repository (Port)                          Query-Optimized Store
                  ↓                                            ↓
           PostgreSQL / MongoDB               Elasticsearch / TimescaleDB / Redis Cache
                  ↓
           Domain Event Published
                  ↓
           Read Model Updater (async)
```

### Separation Rules

| Aspect | Commands | Queries |
|--------|---------|---------|
| Use case naming | `CreateEmployee`, `EscalateAlert`, `CalculateRiskScore` | `GetDashboardSummary`, `SearchActivities`, `ListAlertsByEmployee` |
| Data validation | Full Pydantic + domain entity validation | Minimal (pagination bounds, filter format) |
| Data access | Repository interfaces → PostgreSQL/MongoDB | Direct query handlers → Elasticsearch, TimescaleDB, Redis, read-optimized views |
| Domain events | Yes — publish on state change | No — pure data retrieval |
| Transaction scope | Full ACID via Unit of Work | No transactions needed (read-only) |
| Response shape | Minimal (ID + status) | Rich (denormalized DTOs with nested data) |

### Where CQRS Applies Most

| Module | Command Complexity | Query Complexity | CQRS Benefit |
|--------|-------------------|-----------------|-------------|
| Activity Collection | Low (persist events) | **Very High** (full-text search, filters, timeline) | **High** |
| Alert Management | Medium (generation, routing) | **High** (dashboard aggregations, search) | **High** |
| Reporting & Analytics | Low (schedule reports) | **Very High** (complex analytics, aggregations) | **Very High** |
| Risk Scoring | **High** (ML-based calculation) | Medium (score lookup, trends) | Medium |
| Threat Investigation | **High** (multi-step workflow) | **High** (timeline reconstruction, correlation) | **High** |
| Identity & Access | Medium (CRUD + auth) | Low (user lookup) | Low |

### What This Is NOT

This is **not** full Event Sourcing. We are not storing all state changes as events. We use traditional state-based persistence for commands and maintain separate read-optimized projections for complex queries. Domain events are the bridge that keeps read models eventually consistent with write models.

## Consequences

### Positive
- **Optimized reads**: Dashboard and search queries hit read-optimized stores (Elasticsearch for full-text, TimescaleDB for time-series, Redis for cached aggregations) instead of contending with write transactions on PostgreSQL.
- **Independent scaling**: Read and write paths can be scaled independently. Add more Elasticsearch nodes for search; add more PostgreSQL replicas for write capacity.
- **Clearer use case boundaries**: Each use case is either a Command or a Query — never both. This enforces single-responsibility and makes code easier to understand and test.
- **Performance isolation**: Heavy reporting queries cannot slow down real-time alert generation because they read from different stores.
- **Natural fit for the data pipeline**: Processed events from Kafka update both the write model (MongoDB via Activity Collection) and read models (Elasticsearch indices) simultaneously.

### Negative
- **Eventual consistency**: Read models may lag behind write models by milliseconds to seconds. SOC analysts might not see a just-created alert immediately on the dashboard. Mitigated by WebSocket push for real-time critical updates.
- **Read model maintenance**: Each read-optimized projection (Elasticsearch index, TimescaleDB aggregate, Redis cache) must be kept in sync with the write model. Adds operational overhead and potential for drift.
- **Increased code volume**: Separate command/query handlers, separate DTOs, separate data access logic. More files, more code paths to maintain.
- **Debugging complexity**: A bug in dashboard data requires tracing through: write → domain event → read model updater → read store → query handler. More moving parts than a simple read from the same database that was written to.

## Alternatives Considered

### 1. Traditional CRUD (Same Model for Reads and Writes)
- **Pros**: Simple, one model per entity, no eventual consistency.
- **Cons**: Dashboard queries joining alerts + risk scores + activities across PostgreSQL and MongoDB would either be slow (cross-store correlation in application code) or impossible (no cross-DB joins). Complex reporting would contend with transactional writes.
- **Rejected because**: The system's polyglot persistence strategy (ADR-003) makes cross-store reads unavoidable. CQRS provides the architectural pattern to handle this cleanly.

### 2. Full Event Sourcing + CQRS
- **Pros**: Complete audit trail (every state change is an event). Time-travel debugging. Perfect for forensic analysis.
- **Cons**: Dramatic increase in complexity. Event schema evolution is notoriously difficult. Rebuilding read models from event history can be slow. Requires an event store (EventStoreDB or custom). Steep learning curve for the team.
- **Rejected because**: The audit logging middleware (ADR-002) already captures all mutations. Full event sourcing is overkill for our use case and would significantly delay delivery. Can be adopted for specific modules later if needed.

### 3. Database Views / Materialized Views Only
- **Pros**: PostgreSQL materialized views can pre-compute aggregations without application-level CQRS.
- **Cons**: Only works within a single database. Cannot create a materialized view that joins PostgreSQL with MongoDB or Elasticsearch. View refresh can be expensive and block writes.
- **Rejected because**: Dashboard queries span multiple data stores. Materialized views are used as a tactic within PostgreSQL-only queries but cannot replace the need for cross-store read models.
