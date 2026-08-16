# ADR-008: Elasticsearch for Search and Analytics

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

SOC analysts and security managers need to search, filter, and analyze large volumes of security data in near real-time:

1. **Activity log search**: "Show me all file access events by employee John Doe between June 1–15, on devices tagged as 'restricted', where file size exceeded 100MB" — across potentially millions of records.
2. **Alert search**: "Find all HIGH severity alerts in the last 30 days involving VPN access from countries outside the employee's home country" — with faceted filtering by severity, type, status, assignee.
3. **Investigation search**: "Search case notes and evidence descriptions containing 'exfiltration' across all open investigations" — full-text search with relevance ranking.
4. **Audit log search**: "Show all administrative actions by user admin@corp.com in the last 24 hours" — compliance-driven access to every system mutation.
5. **Dashboard analytics**: Real-time aggregations (alert count by severity, activity volume by hour, top-risk departments) powering the SOC dashboard.

**Key tensions:**
- PostgreSQL can perform full-text search (GIN indexes on `tsvector`), but performance degrades significantly beyond a few million rows, especially with complex multi-field queries and faceted filtering.
- MongoDB supports text search and aggregation pipelines, but its text search lacks Elasticsearch's relevance scoring, highlighting, fuzzy matching, and analyzer chain (stop words, stemming, synonyms).
- Activity logs (stored in MongoDB) and alerts (stored in PostgreSQL) need to be searchable from a single search interface. No single database provides cross-store search.
- The Data Processing & Streaming Layer generates enriched events that must be indexed for search within seconds of ingestion.

## Decision

Adopt **Elasticsearch** as the dedicated search engine and analytics store, operating as a **read-optimized secondary index** alongside PostgreSQL and MongoDB as primary data stores.

### Index Design

| Index | Source Data | Primary Key | Update Strategy |
|-------|-----------|-------------|----------------|
| `itbis-activities-YYYY.MM` | Activity events (MongoDB) | `activity_id` | Written by the data pipeline via Kafka consumer; time-based index rotation |
| `itbis-alerts` | Alerts (PostgreSQL + MongoDB) | `alert_id` | Updated on domain events (`AlertGenerated`, `AlertEscalated`, `AlertClosed`) |
| `itbis-investigations` | Investigations (PostgreSQL) | `incident_id` | Updated on domain events (`InvestigationOpened`, `EvidenceAttached`) |
| `itbis-audit-YYYY.MM` | Audit log entries (middleware) | `audit_id` | Written by audit middleware after each request; time-based rotation |
| `itbis-employees` | Employee profiles (PostgreSQL) | `employee_id` | Updated on domain events (`EmployeeOnboarded`, `EmployeeOffboarded`) |

### Data Flow into Elasticsearch

```
1. Activity Events (high-volume):
   Kafka processed-events topic → Kafka consumer → Elasticsearch bulk API → itbis-activities index

2. Alerts, Investigations, Employees (low-volume):
   Domain Event raised → Event Bus handler → Elasticsearch single-doc API → respective index

3. Audit Logs (medium-volume):
   Audit Middleware → Elasticsearch bulk API (batched) → itbis-audit index
```

### Search Architecture (CQRS Read Side)

```
SOC Analyst → Frontend Search UI
                    ↓
              API Gateway
                    ↓
         Search Query Handler (Application Layer)
                    ↓
         Elasticsearch Client (Infrastructure Layer)
                    ↓
         Elasticsearch Cluster
                    ↓
         Search Results (with highlights, facets, aggregations)
```

Search queries bypass the domain layer entirely — they are read-only queries on a secondary index (per CQRS, ADR-005).

### Elasticsearch Client

- **Library**: `elasticsearch[async]` (official async Python client)
- **Connection**: Managed in `app/infrastructure/database/elasticsearch/client.py`
- **Index management**: Automated index creation, mapping updates, and lifecycle policies in `app/infrastructure/database/elasticsearch/index_manager.py`
- **Search port**: Each module that supports search defines an `XxxSearchPort` interface in its domain layer (e.g., `AlertSearchPort`), implemented by an Elasticsearch adapter in infrastructure.

### Index Lifecycle Management

| Index Pattern | Rotation | Retention | Replicas |
|--------------|----------|-----------|---------|
| `itbis-activities-*` | Monthly | 12 months (configurable) | 1 |
| `itbis-audit-*` | Monthly | 36 months (compliance) | 1 |
| `itbis-alerts` | None (single index) | Indefinite | 1 |
| `itbis-investigations` | None (single index) | Indefinite | 1 |
| `itbis-employees` | None (single index) | Indefinite | 1 |

Time-based indices use Elasticsearch's Index Lifecycle Management (ILM) to automatically transition from hot → warm → cold → delete phases.

## Consequences

### Positive
- **Sub-second search across millions of records**: Elasticsearch is purpose-built for full-text search with inverted indexes. Queries that would take seconds in PostgreSQL return in milliseconds.
- **Rich query capabilities**: Fuzzy matching (catch typos in search), highlighting (show matched terms in context), faceted aggregations (count alerts by severity, department, time range), geo queries (map employee login locations).
- **Unified search interface**: Activity events (from MongoDB), alerts (from PostgreSQL), and audit logs (from middleware) are all searchable through a single Elasticsearch API. The frontend doesn't need to know which primary store holds the data.
- **Real-time analytics**: Dashboard widgets powered by Elasticsearch aggregations (date histograms, terms aggregations, percentiles) update in near real-time without impacting transactional databases.
- **Horizontal scaling**: Elasticsearch clusters scale by adding nodes. Sharding and replication are built-in.
- **Natural CQRS fit**: Elasticsearch serves as the read-optimized store in the CQRS pattern (ADR-005). Writes go to PostgreSQL/MongoDB; reads come from Elasticsearch.

### Negative
- **Data duplication**: Every indexed record exists in both the primary store (PostgreSQL/MongoDB) and Elasticsearch. Storage cost increases, and synchronization must be maintained.
- **Eventual consistency**: There's a delay (typically < 1 second, up to Elasticsearch's `refresh_interval` of 1s by default) between a write to the primary store and its availability in Elasticsearch search results.
- **Operational complexity**: Elasticsearch requires cluster management, shard allocation tuning, index lifecycle policies, and monitoring. More infrastructure to operate than PostgreSQL alone.
- **Resource intensive**: Elasticsearch nodes require significant RAM (JVM heap) and fast storage (SSDs). Minimum production deployment: 3 nodes with 8GB heap each.
- **Schema evolution challenges**: Changing an Elasticsearch mapping (e.g., adding a new field type) may require reindexing. Mitigated by dynamic mapping for new fields and explicit mapping only for fields with specific analyzer requirements.
- **Not a primary data store**: Elasticsearch should never be the sole store for any data. It's an index, not a database. Data recovery comes from the primary stores.

## Alternatives Considered

### 1. PostgreSQL Full-Text Search Only
- **Pros**: No additional infrastructure. PostgreSQL's `tsvector` + GIN indexes provide basic full-text search. Stays within the same transactional boundary.
- **Cons**: Performance degrades beyond ~5M rows for complex queries. No fuzzy matching, no highlighting, no relevance scoring. Cannot search across PostgreSQL and MongoDB data simultaneously. No native aggregation framework comparable to Elasticsearch's.
- **Rejected because**: Activity logs alone will generate millions of records per month. SOC analysts need sub-second search with rich filtering, facets, and highlighting that PostgreSQL cannot provide at scale.

### 2. MongoDB Atlas Search (Lucene-Based)
- **Pros**: Built into MongoDB Atlas. No additional infrastructure for MongoDB-hosted data. Uses Lucene under the hood.
- **Cons**: Only searches data stored in MongoDB. Cannot index PostgreSQL data (alerts, investigations, employees). Requires MongoDB Atlas (cloud-only), conflicting with on-premise deployment requirements. Less mature than Elasticsearch's query DSL and aggregation framework.
- **Rejected because**: The system must search across data from multiple primary stores, not just MongoDB. Additionally, on-premise deployment is a requirement.

### 3. Apache Solr
- **Pros**: Mature, battle-tested full-text search engine. Same underlying technology (Lucene) as Elasticsearch.
- **Cons**: Less modern API (XML-based configuration). Smaller ecosystem of modern client libraries. Less native support for analytics-style aggregations. Kubernetes deployment is less well-supported than Elasticsearch.
- **Rejected because**: Elasticsearch has a larger community, better Python client support, more modern REST API, and stronger analytics aggregation capabilities. The team's expertise aligns with Elasticsearch.

### 4. Typesense / Meilisearch (Lightweight Search)
- **Pros**: Easy to set up, fast typo-tolerant search, modern API.
- **Cons**: Designed for user-facing search (e-commerce, documentation), not security analytics. Lack enterprise-grade aggregation framework, index lifecycle management, and horizontal scaling. Cannot handle the analytical dashboard queries (date histograms, multi-level aggregations).
- **Rejected because**: The system needs Elasticsearch's analytical aggregation framework for dashboard widgets, not just text search.
