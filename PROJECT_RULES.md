# ITBIS — Project Rules & Governance

## Project Identity

**Project Name:** ITBIS — Insider Threat Behavioral Intelligence System  
**Classification:** Enterprise Cybersecurity Platform  
**Architecture:** Modular Monolith (microservice-ready boundaries)  
**Status:** Active Development

---

## ⚠️ CRITICAL CONTEXT RULE

> **This project is ONLY the cybersecurity / insider threat project described below.**
>
> DO NOT use, reference, import, reuse, or mix anything from any food freshness,  
> fruit classification, image classification, CNN, computer vision, or food-related project.
>
> There is a completely separate project involving food freshness classification.  
> That project is **NOT** part of this repository and must **NEVER** appear in this project's  
> architecture, code, documentation, database schema, frontend, or ML pipeline.

---

## 1. Architecture Principles

### 1.1 Modular Monolith First
- Begin as a single FastAPI application with clearly bounded internal modules.
- Each module must remain internally isolated — no cross-module direct imports except through defined interfaces.
- Modules must be designed so they can be extracted into independent microservices later without refactoring their internal logic.

### 1.2 Clean Architecture per Module
Every major module must follow:
```
domain/          # Entities, value objects, domain events, interfaces
application/     # Use cases, commands, queries, DTOs
infrastructure/  # Database repos, external clients, adapters
presentation/    # API routers, request/response schemas
```

### 1.3 API Versioning
- All REST endpoints must be versioned: `/api/v1/...`
- Never expose unversioned endpoints in production.

---

## 2. Technology Constraints

| Layer | Approved Technology |
|---|---|
| Backend Language | Python 3.11+ |
| API Framework | FastAPI |
| ORM | SQLAlchemy (async) |
| Migrations | Alembic |
| Relational DB | PostgreSQL |
| Document DB | MongoDB (Motor async) |
| Search | Elasticsearch |
| Cache / Session | Redis |
| Message Queue | Kafka |
| Object Storage | MinIO (S3-compatible) |
| Data Validation | Pydantic v2 |
| Auth | JWT (access + refresh tokens) |
| Authorization | RBAC with permission checks |
| Frontend | React + TypeScript + Vite |
| UI Component Library | Material UI (MUI) v5 |
| HTTP Client | Axios |
| State Management | React Query |
| Charts | Recharts |
| Containerization | Docker + Docker Compose |
| Testing (BE) | pytest + pytest-asyncio |
| Testing (FE) | Vitest + React Testing Library *(not yet set up — see §11)* |
| Analytics DB | TimescaleDB (PostgreSQL extension) |
| ML | scikit-learn, pandas, numpy (future) |

**Do NOT introduce new technologies without explicit approval.**

> **Stack note (2026-09-14).** The frontend was built with **Material UI**, not
> the Tailwind CSS originally listed here. MUI is used across 21 components;
> Tailwind survives in 2 files plus its config. This table now records the
> decision that was actually made. Remaining work: either remove the unused
> Tailwind/PostCSS config, or deliberately re-adopt it.

---

## 3. Development Principles

### 3.1 Incremental Implementation
- NEVER attempt to implement the entire system in one step.
- Each implementation phase: Inspect → Understand → Preserve → Implement → Test → Fix → Document.
- Do not rewrite working modules.
- Do not change architectural decisions without asking.

### 3.2 SOLID Principles
- **S**ingle Responsibility: Each class/module has one reason to change.
- **O**pen/Closed: Open for extension, closed for modification.
- **L**iskov Substitution: Subtypes must be substitutable for their base types.
- **I**nterface Segregation: Clients should not depend on interfaces they don't use.
- **D**ependency Inversion: Depend on abstractions, not concretions.

### 3.3 Patterns
- Repository Pattern for all data access.
- Dependency Injection via FastAPI's `Depends()`.
- Unit of Work for transactional consistency.
- Domain Events for inter-module communication.
- CQRS where the complexity warrants it.

---

## 4. Security Requirements

- All passwords: bcrypt hashed (via passlib).
- JWT authentication: short-lived access tokens + refresh tokens.
- Token blacklist: Redis.
- RBAC: Enforced at every protected endpoint.
- Input validation: Pydantic models on every request.
- CORS: Explicitly configured — no wildcard in production.
- Rate limiting: Applied to auth and sensitive endpoints.
- Audit logging: Every security-relevant action must be logged.
- No hardcoded credentials anywhere in code.
- No secrets committed to Git — use `.env` files (excluded by `.gitignore`).
- Proper error handling: Never expose stack traces or internal messages to clients.

---

## 5. Data Storage Responsibilities

| Store | Responsibilities |
|---|---|
| **PostgreSQL** | Users, Roles, Permissions, Employees, Departments, Assets, Policies, Investigations, Alerts, Workflows, Configuration |
| **MongoDB** | High-volume activity documents, Flexible event data, Enriched events, Case notes |
| **Elasticsearch** | Fast activity searching, Security-event searching, Alert searching, Investigation queries |
| **Redis** | Cache, Sessions, Token blacklist, Feature-store aggregates, Short-lived behavioral data |
| **MinIO** | Evidence files, Reports, Raw datasets/log archives, Backups |
| **TimescaleDB** | Time-series analytics, Behavioral metrics over time |

---

## 6. Module Boundaries

The following modules exist within the monolith. Each is independently bounded:

| Module | Responsibility |
|---|---|
| `identity` | Authentication, Authorization, RBAC |
| `users` | User management, employee profiles |
| `assets` | Device inventory, asset tracking |
| `activity` | Log ingestion, normalization, event streaming |
| `behavioral` | Baseline profiling, peer-group modeling |
| `anomaly` | Anomaly detection, ML model management |
| `risk` | Risk scoring, score explanation |
| `ueba` | UEBA intelligence, entity risk |
| `alerts` | Alert generation, deduplication, routing |
| `investigations` | Incident timeline, evidence, case management |
| `response` | Playbooks, automation, SOAR integration |
| `reporting` | Report generation, scheduled reports |
| `notifications` | Email, SMS, Slack, in-app notifications |
| `admin` | System configuration, audit logs |

**Implementation status.** Seven modules are built out
(`identity`, `activity`, `behavioral`, `anomaly`, `alerts`, `investigations`,
`reporting`). The remaining seven (`users`, `assets`, `risk`, `ueba`,
`response`, `notifications`, `admin`) are directory scaffolds with empty
`__init__.py` files and no routers mounted. Treat the table above as the
target architecture, not the current state.

---

## 7. Dataset Rules

- The **CERT Insider Threat Dataset** is the initial development dataset.
- Do not assume schema uniformity across CERT dataset versions.
- All dataset connectors must use the adapter pattern.
- All raw data must be normalized to the **Canonical Event Schema** before processing.

---

## 8. Code Quality Standards

- All Python code must pass `ruff` linting.
- All Python code must be type-annotated.
- All public functions must have docstrings.
- Test coverage target: ≥ 80% per module.
- All API changes must be documented in the OpenAPI schema.
- No `print()` statements in production code — use structured logging.

---

## 9. Git Conventions

- Branch naming: `feature/<module>/<description>`, `fix/<module>/<description>`
- Commit format: `<type>(<scope>): <description>` (Conventional Commits)
- No direct commits to `main`.
- PRs require at least one review.
- No secrets, credentials, or large datasets committed to Git.

---

## 10. What This Project Is NOT

- NOT an antivirus or endpoint protection system.
- NOT a firewall, WAF, IDS/IPS, or network security system.
- NOT a food freshness, fruit classification, or image classification system.
- NOT a SIEM (though it may integrate with one).
- NOT a replacement for existing security tooling.

---

## 11. Known Deviations from These Rules

Tracked honestly rather than quietly ignored:

| Rule | Deviation | Status |
|---|---|---|
| §2 Frontend styling | MUI used instead of Tailwind | Rules updated to match reality; stale Tailwind config still to remove |
| §2 Testing (FE) | No frontend tests exist; Vitest not installed | Open — backend/agent are covered, frontend is not |
| §8 Coverage ≥80% per module | Not enforced in CI | Open |
| §9 Git conventions | Work is committed directly to `master` | Open |
| Data pipeline | Kafka, Elasticsearch, MinIO and TimescaleDB run in Docker but nothing connects to them | Open — infrastructure is provisioned ahead of use |

---

*Last updated: 2026-09-14*
