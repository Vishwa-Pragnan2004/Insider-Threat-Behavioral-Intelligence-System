# ITBIS — Architecture Overview

## System Architecture

ITBIS uses a **Modular Monolith** architecture initially.
This maximises development velocity while maintaining the clean boundaries required for future microservice extraction.

```
┌───────────────────────────────────────────────────────────────┐
│                   React Frontend (Vite + TypeScript)          │
│   SOC Dashboard · Alerts · Investigations · Risk Profiles     │
└────────────────────────────┬──────────────────────────────────┘
                             │ REST HTTP  /api/v1/*
┌────────────────────────────▼──────────────────────────────────┐
│                    FastAPI Application                        │
│                   (Modular Monolith)                          │
│                                                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │
│  │   identity   │ │    users     │ │       assets         │  │
│  │   (auth/rbac)│ │  (employees) │ │  (devices/inventory) │  │
│  └──────────────┘ └──────────────┘ └──────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │
│  │   activity   │ │  behavioral  │ │       anomaly        │  │
│  │(log ingest)  │ │  (profiling) │ │ (isolation forest)   │  │
│  └──────────────┘ └──────────────┘ └──────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │
│  │     risk     │ │     ueba     │ │       alerts         │  │
│  │  (scoring)   │ │(intelligence)│ │  (management)        │  │
│  └──────────────┘ └──────────────┘ └──────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │
│  │investigations│ │   response   │ │      reporting       │  │
│  │  (cases)     │ │ (workflows)  │ │   (analytics)        │  │
│  └──────────────┘ └──────────────┘ └──────────────────────┘  │
│  ┌──────────────┐ ┌──────────────────────────────────────┐   │
│  │notifications │ │              admin                   │   │
│  │(email/slack) │ │   (configuration, audit logs)        │   │
│  └──────────────┘ └──────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────┐
│                       Data Layer                              │
│                                                               │
│  PostgreSQL 16    │  MongoDB 7       │  Elasticsearch 8       │
│  (relational)     │  (documents)     │  (search)              │
│                                                               │
│  Redis 7          │  Kafka           │  MinIO                 │
│  (cache/sessions) │  (event stream)  │  (object storage)      │
│                                                               │
│  TimescaleDB      │                                           │
│  (time-series)    │                                           │
└───────────────────────────────────────────────────────────────┘
```

## Module Internal Structure

Each module follows Clean Architecture with four layers:

```
modules/<module>/
├── domain/
│   ├── entities/          # Core business objects
│   ├── value_objects/     # Immutable domain primitives
│   ├── events/            # Domain events
│   └── repositories/      # Repository interfaces (abstractions)
│
├── application/
│   ├── use_cases/         # Business logic use cases
│   ├── commands/          # Write commands (CQRS)
│   ├── queries/           # Read queries (CQRS)
│   └── dtos/              # Data transfer objects
│
├── infrastructure/
│   ├── repositories/      # Concrete repository implementations
│   ├── models/            # SQLAlchemy / Motor ORM models
│   └── adapters/          # External service adapters
│
└── presentation/
    ├── router.py          # FastAPI router
    ├── schemas.py         # Pydantic request/response schemas
    └── dependencies.py    # FastAPI dependency injections
```

## Data Flow

```
Incoming Request
      │
      ▼
FastAPI Router (presentation/)
      │
      ▼
  Use Case (application/)
      │
      ├── Repository Interface (domain/)
      │         │
      │         ▼
      │   Concrete Repository (infrastructure/)
      │         │
      │         ▼
      │    Database / External Service
      │
      ├── Domain Events (domain/)
      │
      └── Response DTO (application/)
            │
            ▼
     Pydantic Schema (presentation/)
            │
            ▼
       HTTP Response
```

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Modular Monolith | Fast development, extractable later |
| Internal pattern | Clean Architecture | Testability, separation of concerns |
| Data access | Repository Pattern | Swap backends without changing use cases |
| Dependencies | FastAPI `Depends()` | Native DI, testable |
| Event-driven | Domain Events | Decouple modules without direct imports |
| API style | REST + JSON | Simplicity, broad tooling support |
| API versioning | `/api/v1/` | Non-breaking future evolution |
| Auth | JWT | Stateless, scalable |
| Authorization | RBAC | Role-based, audit-friendly |
