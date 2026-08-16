# ADR-006: Repository Pattern

**Status**: Accepted  
**Date**: 2026-07-21  
**Decision Makers**: Architecture Team  

---

## Problem

The system uses multiple data stores (PostgreSQL, MongoDB, Elasticsearch, Redis) across 12 service modules. Each module's domain logic must interact with persistence without being coupled to any specific database technology.

**Key tensions:**
- Domain entities are pure Python objects with business invariants. They must not contain SQLAlchemy column definitions, MongoDB document schemas, or Elasticsearch mapping annotations.
- The same conceptual operation ("save an alert") may write to PostgreSQL (structured data) and Elasticsearch (search index) simultaneously.
- AI/ML modules (Behavioral Profiling, Anomaly Detection, Risk Scoring) will be added later and may need to access data from repositories already built — the interface must be stable.
- Testing domain logic and use cases requires fast, in-memory test doubles for persistence. If use cases depend directly on SQLAlchemy sessions or Motor clients, tests become slow integration tests.

## Decision

Adopt the **Repository Pattern** with explicit separation between abstract interfaces (ports) and concrete implementations (adapters).

### Structure per Module

```
module/
├── domain/
│   └── interfaces/
│       ├── user_repository.py          # Abstract interface (Port)
│       └── identity_provider.py        # Abstract external service port
│
└── infrastructure/
    └── repositories/
        ├── pg_user_repository.py       # PostgreSQL implementation (Adapter)
        └── (future) cache_user_repository.py  # Redis-cached decorator
```

### Repository Interface Contract

Every repository interface follows these rules:

1. **Defined in the domain layer** as an abstract base class (ABC)
2. **Uses domain entities and value objects** as parameters and return types — never ORM models or raw dicts
3. **Named by domain concept**, not by technology: `UserRepository`, not `SQLAlchemyUserRepository`
4. **Provides domain-meaningful methods**: `find_by_email()`, `find_active_by_department()`, not `execute_query()`

Example contract:
```python
from abc import ABC, abstractmethod
from uuid import UUID
from app.modules.identity.domain.entities.user import User

class UserRepository(ABC):
    @abstractmethod
    async def find_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def find_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def delete(self, user_id: UUID) -> None: ...
```

### Implementation Contract

Every repository implementation follows these rules:

1. **Defined in the infrastructure layer**, never imported by the domain
2. **Handles ORM model ↔ domain entity mapping** internally
3. **Named by technology**: `PgUserRepository`, `MongoActivityRepository`, `EsAlertSearchRepository`
4. **Injected via FastAPI's dependency system** in `core/dependencies.py`

### Generic Base Repository

A `BaseRepository[T]` generic class in `app/shared/infrastructure/base_repository.py` provides default CRUD operations for PostgreSQL-backed repositories to reduce boilerplate:

```python
class BaseRepository(Generic[ModelType, EntityType]):
    async def find_by_id(self, id: UUID) -> EntityType | None: ...
    async def save(self, entity: EntityType) -> EntityType: ...
    async def delete(self, id: UUID) -> None: ...
    async def find_all(self, skip: int, limit: int) -> list[EntityType]: ...
```

Module-specific repositories extend this base and add domain-specific query methods.

### Dependency Injection Wiring

```python
# core/dependencies.py
from app.modules.identity.domain.interfaces.user_repository import UserRepository
from app.modules.identity.infrastructure.repositories.pg_user_repository import PgUserRepository

def get_user_repository(session = Depends(get_db_session)) -> UserRepository:
    return PgUserRepository(session)
```

Use cases receive repositories through constructor injection:
```python
class LoginUseCase:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
```

## Consequences

### Positive
- **Domain purity**: Domain entities and use cases have zero knowledge of SQLAlchemy, Motor, or Elasticsearch. They depend only on abstract interfaces.
- **Testability**: Use cases can be unit-tested with in-memory fake repositories. No database setup, no Docker containers, sub-millisecond test execution.
- **Technology swappability**: Replacing PostgreSQL with another relational database only requires a new repository implementation. The domain layer and all use cases remain unchanged.
- **Multi-store transparency**: The Threat Investigation module's `IncidentRepository` can internally write to PostgreSQL while `CaseNoteRepository` writes to MongoDB. Use cases don't know or care.
- **Decorator pattern**: Caching can be added as a repository decorator (`CachedUserRepository` wrapping `PgUserRepository`) without modifying any existing code.
- **Consistent API**: All modules follow the same repository contract pattern, making it easy for developers to move between modules.

### Negative
- **Mapping boilerplate**: Every repository must convert between domain entities and ORM models (or MongoDB documents). For an entity with 15 fields, this means 15 lines of mapping code in each direction.
- **Abstraction overhead**: For simple CRUD modules (Notification Service), the repository abstraction adds files and indirection without meaningful benefit. Accepted as a consistency trade-off.
- **Risk of anemic repositories**: If not careful, repositories become thin wrappers around ORM queries with no domain value. Domain-specific query methods (e.g., `find_employees_with_risk_above(threshold)`) prevent this.
- **Interface proliferation**: 12 modules × 2-4 repositories each = 24-48 abstract interfaces to maintain. Mitigated by the generic base repository reducing per-interface method count.

## Alternatives Considered

### 1. Active Record Pattern (ORM Models as Domain Entities)
- **Pros**: No mapping code. SQLAlchemy models are the entities. Less boilerplate.
- **Cons**: Domain logic is coupled to SQLAlchemy. Cannot unit-test domain logic without a database. Cannot swap to MongoDB for a module's persistence without rewriting domain logic. ORM concerns (lazy loading, session management) leak into business logic.
- **Rejected because**: The polyglot persistence strategy (ADR-003) means some modules use PostgreSQL and others use MongoDB. Active Record locks the domain to a single ORM.

### 2. Data Mapper Without Repository Abstraction
- **Pros**: SQLAlchemy's Data Mapper pattern (separate ORM models from domain entities) provides the mapping benefit without the repository interface.
- **Cons**: Use cases would depend directly on SQLAlchemy sessions, making them untestable without a database and impossible to swap to MongoDB.
- **Rejected because**: We need the interface abstraction to support multiple data stores and enable fast unit testing.

### 3. Query Objects / Specification Pattern
- **Pros**: Highly flexible querying — domain defines specifications, infrastructure translates to SQL/MongoDB queries.
- **Cons**: Significantly more complex to implement. Specification-to-query translation is error-prone and hard to optimize. Over-engineering for most modules.
- **Decision**: Not rejected, but **deferred**. Can be introduced for the Activity Collection module's complex search requirements alongside Elasticsearch, where the Specification pattern maps naturally to Elasticsearch query DSL.
