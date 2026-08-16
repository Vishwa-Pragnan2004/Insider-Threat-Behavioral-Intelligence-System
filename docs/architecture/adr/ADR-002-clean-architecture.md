# ADR-002: Clean Architecture

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

Each of the 12 service modules within the modular monolith needs an internal code organization strategy. The system has complex requirements:

- Business logic must be testable in isolation, without databases, HTTP frameworks, or external services.
- Multiple data stores (PostgreSQL, MongoDB, Elasticsearch, Redis) must be swappable per module without affecting business logic.
- AI/ML components (Behavioral Profiling, Anomaly Detection, Risk Scoring, UEBA) will be integrated later and must plug in without refactoring existing code.
- External system integrations (LDAP, SIEM, SOAR, EDR, DLP) vary by customer deployment and must be interchangeable.
- The system will evolve over years; architectural decisions made now must support long-term maintainability.

**Key tensions:**
- FastAPI and SQLAlchemy are powerful but encourage tight coupling between HTTP handling, business logic, and database access if not carefully structured.
- Domain logic for insider threat detection (risk scoring algorithms, anomaly thresholds, alert deduplication rules) is complex and must not be entangled with infrastructure concerns.
- Different modules have different infrastructure needs (Activity Collection uses MongoDB; Identity uses PostgreSQL), but their domain logic should follow the same structural patterns.

## Decision

Adopt **Clean Architecture** (Ports and Adapters / Hexagonal Architecture) as the internal structure for every service module. Each module contains four layers with strict dependency rules:

```
presentation/ → application/ → domain/ ← infrastructure/
```

### Layer Responsibilities

| Layer | Contains | Depends On | Never Depends On |
|-------|----------|-----------|-----------------|
| **Domain** | Entities, Value Objects, Domain Events, Repository Interfaces (Ports), Domain Services | Nothing (pure Python) | Application, Infrastructure, Presentation, any framework |
| **Application** | Use Cases, Pydantic Schemas (DTOs), Application Services | Domain layer only | Infrastructure, Presentation |
| **Infrastructure** | ORM Models, Repository Implementations (Adapters), External Service Adapters, Database Clients | Domain (implements interfaces), Application (reads DTOs) | Presentation |
| **Presentation** | FastAPI Routers, Request/Response handling | Application (calls use cases) | Domain internals, Infrastructure internals |

### The Dependency Rule

Dependencies point **inward** only. The domain layer is at the center and has zero external dependencies. Infrastructure implements domain interfaces via Dependency Inversion.

### Ports and Adapters

- **Ports** (in `domain/interfaces/`): Abstract base classes defining what the domain needs (e.g., `UserRepository`, `AIEnginePort`, `NotificationPort`).
- **Adapters** (in `infrastructure/`): Concrete implementations (e.g., `PgUserRepository`, `MongoActivityRepository`, `LDAPProvider`).
- Binding happens in `core/dependencies.py` via FastAPI's dependency injection system.

## Consequences

### Positive
- **Framework independence**: Domain logic has zero dependency on FastAPI, SQLAlchemy, or any external library. If we ever need to swap FastAPI for another framework, only the presentation layer changes.
- **Testability**: Domain entities and use cases can be unit-tested with in-memory fakes. No database, no HTTP server, no external services needed for 80% of tests.
- **AI plug-in readiness**: AI/ML engines are defined as domain ports (`AIEnginePort`, `ScoringEnginePort`). When implemented, they are injected as infrastructure adapters — zero changes to domain or application layers.
- **Infrastructure swappability**: Switching from PostgreSQL to another relational DB, or from Motor to PyMongo, only touches the infrastructure layer.
- **Consistent structure**: All 12 modules follow the same pattern. A developer who understands one module can navigate any other module immediately.

### Negative
- **More boilerplate**: Each module requires interfaces, implementations, and DI wiring even for simple CRUD operations. A simple entity requires files in 4 layers.
- **Mapping overhead**: Domain entities must be mapped to/from ORM models (infrastructure) and DTOs (application). This adds code but prevents ORM concerns from leaking into the domain.
- **Learning curve**: Developers unfamiliar with Clean Architecture need onboarding. The strict layer rules can feel constraining initially.
- **Over-engineering risk for simple modules**: Notification Service's domain logic is simpler than Risk Scoring's, but both follow the same structure. Accepted as a consistency trade-off.

## Alternatives Considered

### 1. Traditional Layered Architecture (Controller → Service → Repository)
- **Pros**: Familiar, less boilerplate, widely understood.
- **Cons**: No dependency inversion. Services depend directly on repository implementations. Business logic tends to migrate into service classes that also handle HTTP concerns. Swapping infrastructure requires touching business logic.
- **Rejected because**: The system's complexity (6 data stores, future AI/ML integration, multiple external system adapters) demands strict separation that traditional layers don't enforce.

### 2. Domain-Driven Design (DDD) Tactical Patterns Only
- **Pros**: Rich domain modeling (Aggregates, Bounded Contexts, Specifications).
- **Cons**: DDD tactical patterns are complementary to, not a replacement for, architectural layering. Using DDD entities inside a flat architecture still results in coupled infrastructure.
- **Decision**: We adopt DDD tactical patterns (Entities, Value Objects, Domain Events, Aggregate Roots) **within** Clean Architecture's domain layer. They are complementary, not competing approaches.

### 3. Feature-Slice Architecture (Vertical Slices)
- **Pros**: Each feature is a self-contained vertical slice (handler + query + model). Reduces indirection.
- **Cons**: Works well for CRUD-heavy applications but struggles with complex domain logic that spans multiple features. Risk scoring, anomaly detection, and UEBA require shared domain concepts that don't fit neatly into isolated slices.
- **Rejected because**: The AI/ML services have rich domain logic with cross-cutting behavioral analysis that benefits from a shared domain layer within each module.
