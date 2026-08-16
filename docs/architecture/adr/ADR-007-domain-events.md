# ADR-007: Domain Events

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

The 12 service modules in the modular monolith need to communicate state changes without creating direct dependencies between them. The corrected event flow defines a unidirectional chain:

```
Activity Collection → Behavioral Profiling → Anomaly Detection → Risk Scoring
→ UEBA Intelligence → Alert Management → Threat Investigation → Response & Workflow
→ Reporting & Analytics
```

Additionally, cross-cutting concerns react to events from multiple modules:
- **Notification Service** must send alerts when any module raises a critical event
- **Audit Middleware** must log all state-changing operations
- **Dashboard** must reflect changes from alerts, risk scores, investigations, and activities

**Key tensions:**
- If Activity Collection directly imports and calls Behavioral Profiling's use case, the two modules become tightly coupled. Changing Behavioral Profiling's interface breaks Activity Collection.
- The event chain has 9 stages. If each stage synchronously calls the next, a single slow stage blocks the entire pipeline.
- Some events need to trigger multiple reactions (e.g., `RiskThresholdBreached` should simultaneously trigger Alert Management AND Notification Service).
- The modular monolith must be structured so that any module can be extracted into a separate microservice by replacing the in-process event bus with Kafka.

## Decision

Adopt **Domain Events** as the primary inter-module communication mechanism, implemented via an in-process event bus with async dispatch.

### Event Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Activity        │     │   Event Bus      │     │  Behavioral      │
│  Collection      │────▶│                  │────▶│  Profiling       │
│  Service         │     │  - Publish       │     │  Service         │
│                  │     │  - Subscribe     │     │                  │
│  raises:         │     │  - Async dispatch│     │  subscribes to:  │
│  ActivityStored  │     │                  │     │  ActivityStored   │
└──────────────────┘     │                  │     └──────────────────┘
                         │                  │
                         │                  │     ┌──────────────────┐
                         │                  │────▶│  Notification    │
                         │                  │     │  Service         │
                         └──────────────────┘     └──────────────────┘
```

### Domain Event Structure

Every domain event inherits from a base class and carries:

```python
@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID              # Unique event identifier
    event_type: str             # Qualified name (e.g., "activity.activity_stored")
    occurred_at: datetime       # When the event happened
    aggregate_id: UUID          # ID of the entity that raised the event
    aggregate_type: str         # Type of the entity (e.g., "Activity")
    payload: dict               # Event-specific data
    correlation_id: UUID | None # Links related events across the chain
    causation_id: UUID | None   # ID of the event that caused this one
```

### Event Catalog

| Event | Raised By | Consumed By |
|-------|----------|-------------|
| `ActivityStored` | Activity Collection | Behavioral Profiling, Anomaly Detection |
| `BaselineEstablished` | Behavioral Profiling | Anomaly Detection |
| `PatternDeviationDetected` | Behavioral Profiling | Risk Scoring |
| `AnomalyDetected` | Anomaly Detection | Risk Scoring, Alert Management |
| `RiskIndicatorTriggered` | Anomaly Detection | Risk Scoring |
| `RiskScoreCalculated` | Risk Scoring | UEBA Intelligence, Dashboard |
| `RiskThresholdBreached` | Risk Scoring | Alert Management, Notification |
| `ThreatPredicted` | UEBA Intelligence | Alert Management |
| `AlertGenerated` | Alert Management | Threat Investigation, Notification, Dashboard |
| `AlertEscalated` | Alert Management | Notification, Response & Workflow |
| `AlertAcknowledged` | Alert Management | Dashboard |
| `AlertClosed` | Alert Management | Reporting |
| `InvestigationOpened` | Threat Investigation | Dashboard, Notification |
| `InvestigationClosed` | Threat Investigation | Reporting, Response & Workflow |
| `EvidenceAttached` | Threat Investigation | (Audit log only) |
| `PlaybookTriggered` | Response & Workflow | Notification |
| `RemediationCompleted` | Response & Workflow | Reporting |
| `UserCreated` | Identity & Access | User Management, Audit |
| `UserDeactivated` | Identity & Access | Activity Collection, Alert Management |
| `EmployeeOnboarded` | User Management | Behavioral Profiling |
| `EmployeeOffboarded` | User Management | Risk Scoring, Alert Management |

### In-Process Event Bus Implementation

The event bus (`core/event_bus.py`) provides:

1. **Registration**: Modules register handlers for specific event types during application startup
2. **Publishing**: Aggregate roots collect domain events; the Unit of Work publishes them after successful commit
3. **Async dispatch**: Handlers execute asynchronously via `asyncio.create_task()` — the publisher does not wait for handlers to complete
4. **Error isolation**: A failing handler does not affect other handlers or the original transaction
5. **Correlation tracking**: `correlation_id` links the entire chain from `ActivityStored` through `AlertGenerated` for forensic tracing

### Microservice Extraction Path

When a module is extracted into a separate service:
1. The in-process event bus handler is replaced with a Kafka producer
2. The subscribing module's handler is replaced with a Kafka consumer
3. The event payload (serialized as JSON) remains identical
4. The `correlation_id` and `causation_id` provide distributed tracing continuity

## Consequences

### Positive
- **Zero coupling between modules**: Activity Collection has no knowledge of Behavioral Profiling, Alert Management, or any downstream service. It simply raises `ActivityStored` and moves on.
- **Fan-out capability**: A single event (`RiskThresholdBreached`) can trigger Alert Management, Notification Service, and Dashboard updates simultaneously.
- **Auditable event chain**: `correlation_id` links the entire lifecycle: `ActivityStored` → `AnomalyDetected` → `RiskThresholdBreached` → `AlertGenerated` → `InvestigationOpened`. An investigator can trace exactly how an alert was generated.
- **Temporal decoupling**: Handlers run asynchronously. The Activity Collection Service can persist 10,000 events/second without waiting for Behavioral Profiling to process each one.
- **Microservice-ready**: The event-driven architecture maps directly to Kafka topics. Extraction requires only changing the transport, not the logic.
- **Testability**: In tests, the event bus can be replaced with a spy/recorder to verify that the correct events were raised without triggering downstream handlers.

### Negative
- **Eventual consistency**: When Activity Collection stores an event and raises `ActivityStored`, the behavioral profile is not immediately updated. There's a small window of inconsistency. Acceptable for this system — SOC analysts don't need sub-millisecond consistency.
- **Debugging complexity**: An issue in the alert dashboard might originate from a failed handler 5 events upstream in the chain. Correlation IDs mitigate this but don't eliminate the debugging challenge.
- **No guaranteed ordering**: Async dispatch means handlers may execute in any order. If ordering matters, the handler must implement its own sequencing logic (e.g., check `occurred_at` timestamps).
- **Silent failures**: A handler that throws an exception may go unnoticed if not properly logged and monitored. Mitigated by structured logging and dead-letter handling in the event bus.
- **Event schema evolution**: Changing an event's payload structure can break downstream handlers. Mitigated by versioning events and maintaining backward compatibility.

## Alternatives Considered

### 1. Direct Method Calls Between Modules
- **Pros**: Simple, synchronous, easy to debug.
- **Cons**: Creates a dependency graph where changing one module requires updating all callers. Makes it impossible to extract modules into separate services. A slow downstream call blocks the upstream caller.
- **Rejected because**: With 12 modules and the defined event chain having 9 stages, direct calls would create an unmaintainable web of dependencies.

### 2. Mediator Pattern (MediatR-style)
- **Pros**: Decoupled request/handler dispatch. Well-known in .NET ecosystem.
- **Cons**: Typically used for request-response (command → handler → result), not for fire-and-forget event fan-out. Can be adapted but adds indirection without the event semantics (correlation, causation, replay).
- **Rejected because**: Domain events are semantically richer than mediator messages. They carry business meaning (`AlertGenerated`), support correlation tracking, and map directly to Kafka topics for future extraction.

### 3. Kafka for All Inter-Module Communication (Even Within the Monolith)
- **Pros**: Consistent transport whether in monolith or microservices. Durable events. Built-in replay.
- **Cons**: Adds network hops and serialization overhead for in-process communication. Requires Kafka to be running for the application to function, even in development. Over-engineering for modules that run in the same process.
- **Rejected because**: An in-process event bus with identical event contracts provides the same logical decoupling with zero network overhead. Kafka is used for the data pipeline (ADR-004) where its durability and replay capabilities are essential.
