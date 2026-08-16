# ADR-001: Modular Monolith Architecture

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

The system architecture diagram defines 12 distinct microservices (Identity & Access, User & Asset Management, Activity Collection, Behavioral Profiling, Anomaly Detection, Risk Scoring, UEBA Intelligence, Threat Investigation, Alert Management, Response & Workflow, Reporting & Analytics, Notification). We need to decide how to structure these services for incremental, team-friendly development while preserving the ability to scale independently in the future.

**Key tensions:**
- The architecture envisions 12 independent microservices, but the team is building incrementally — one module at a time.
- True microservices from day one would require distributed infrastructure (service discovery, API gateways between services, distributed tracing, per-service databases) before any business value is delivered.
- A traditional monolith would make it difficult to extract services later without significant refactoring.
- The system will eventually handle high-volume data ingestion (activity logs) alongside low-volume CRUD operations (user management), requiring different scaling characteristics.

## Decision

Adopt a **Modular Monolith** architecture where each of the 12 microservices from the system diagram is implemented as a **self-contained module** within a single deployable FastAPI application.

Each module internally follows Clean Architecture with its own:
- `domain/` — entities, value objects, events, repository interfaces
- `application/` — use cases, DTOs/schemas
- `infrastructure/` — ORM models, repository implementations, external adapters
- `presentation/` — FastAPI routers

Modules communicate exclusively through:
1. **Domain Events** via an in-process event bus (no direct imports between module internals)
2. **Shared Kernel** types (value objects, base classes) that live in `app/shared/`

Module boundaries are enforced by convention: a module may only import from `app/shared/`, `app/core/`, and its own internal packages. Cross-module dependencies go through the event bus or dependency injection.

## Consequences

### Positive
- **Incremental delivery**: Each module can be built, tested, and shipped independently within the single deployable.
- **Simpler infrastructure**: One process, one deployment pipeline, one set of database connections — dramatically reduced operational complexity during the build phase.
- **Microservice extraction path**: Because modules have strict boundaries and communicate via events, any module can be extracted into its own service by replacing the in-process event bus with a message broker (Kafka/RabbitMQ) and the shared database with per-service databases.
- **Team-friendly**: Developers can work on separate modules with minimal merge conflicts, since each module owns its own folder subtree.
- **Single transaction boundary**: Cross-module operations (e.g., creating an alert and triggering a notification) can leverage database transactions without distributed transaction complexity.

### Negative
- **Discipline required**: Module boundaries are enforced by convention, not by the compiler or network. Code reviews must guard against cross-module coupling.
- **Shared database risk**: All modules share PostgreSQL (and MongoDB, Elasticsearch, Redis). A poorly-optimized query in one module can impact others. Mitigated by connection pooling and query monitoring.
- **Scaling is all-or-nothing initially**: Cannot scale the Activity Collection module independently from Identity. Mitigated by the extraction path when scaling is needed.
- **Module size growth**: Over time, modules may accumulate complexity. Regular refactoring and adherence to Clean Architecture within each module mitigates this.

## Alternatives Considered

### 1. True Microservices from Day One
- **Pros**: Independent scaling, independent deployability, technology diversity per service.
- **Cons**: Massive upfront infrastructure investment (Kubernetes, service mesh, distributed tracing, per-service CI/CD). Would delay first working feature by months. Overkill for initial team size and traffic volume.
- **Rejected because**: Premature optimization. The modular monolith provides the same logical separation with a fraction of the operational cost, and modules can be extracted when the need is proven.

### 2. Traditional Layered Monolith
- **Pros**: Simple, familiar, fast to start.
- **Cons**: No module boundaries. Domain logic for all 12 services would intermingle. Extracting a service later would require untangling deeply coupled code across shared layers.
- **Rejected because**: The scale of this system (12 services, 6 data stores, AI/ML pipelines) guarantees that a flat monolith would become unmaintainable within 6 months.

### 3. Serverless / Function-as-a-Service
- **Pros**: Auto-scaling, pay-per-invocation.
- **Cons**: Cold start latency is unacceptable for real-time threat detection. Complex stateful workflows (investigations, playbook execution) are difficult to model as stateless functions. Vendor lock-in.
- **Rejected because**: Insider threat detection requires persistent connections (WebSockets for real-time alerts), long-running processes (stream processing), and complex stateful workflows that don't map well to serverless.
