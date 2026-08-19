# 🛡️ ITBIS — Insider Threat Behavioral Intelligence System

<p align="center">
  <img src="docs/assets/itbis-banner.svg" alt="ITBIS Banner" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/React-18+-61DAFB?style=for-the-badge&logo=react" />
  <img src="https://img.shields.io/badge/PostgreSQL-16+-336791?style=for-the-badge&logo=postgresql" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker" />
  <img src="https://img.shields.io/badge/Status-Foundation-orange?style=for-the-badge" />
</p>

---

## Overview

**ITBIS** is an enterprise-grade cybersecurity platform that detects potentially malicious, compromised, or abnormal employee and user behavior using **User and Entity Behavior Analytics (UEBA)**.

The system collects and processes activity logs, establishes behavioral baselines, identifies anomalous behavior, calculates insider risk scores, generates security alerts, and provides SOC/security analysts with investigation and response capabilities.

---

## Key Capabilities (Planned)

| Capability | Description |
|---|---|
| 🔍 **Behavioral Profiling** | Learns normal user behavior and peer-group patterns |
| 🤖 **Anomaly Detection** | Isolation Forest + unsupervised ML for unknown threats |
| ⚠️ **Risk Scoring** | Explainable composite insider risk scores |
| 🚨 **Alert Management** | Deduplication, severity, routing, enrichment |
| 🔎 **Threat Investigation** | Timeline, evidence collection, case management |
| 📊 **SOC Dashboard** | Real-time analyst view of threats and investigations |
| 📋 **Response Workflows** | Playbooks, automation, SOAR integration |
| 📈 **Reporting** | Scheduled and custom security reports |

---

## Threat Categories Detected

- Insider data theft & exfiltration
- Privilege abuse
- Compromised employee accounts
- Unauthorized resource access
- Suspicious login behavior (time, location, device)
- USB / removable media misuse
- Suspicious file activity
- Suspicious email & web activity
- Remote access abuse
- Policy violations

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│              React + TypeScript Frontend         │
│     (SOC Dashboard, Alerts, Investigations)      │
└─────────────────┬───────────────────────────────┘
                  │ REST / HTTP
┌─────────────────▼───────────────────────────────┐
│         FastAPI — Modular Monolith               │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ identity │ │  users   │ │     activity     │ │
│  ├──────────┤ ├──────────┤ ├──────────────────┤ │
│  │behavioral│ │ anomaly  │ │      risk        │ │
│  ├──────────┤ ├──────────┤ ├──────────────────┤ │
│  │  alerts  │ │  ueba    │ │  investigations  │ │
│  ├──────────┤ ├──────────┤ ├──────────────────┤ │
│  │ response │ │reporting │ │  notifications   │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│                  Data Layer                      │
│  PostgreSQL  │  MongoDB  │  Elasticsearch        │
│  Redis       │  Kafka    │  MinIO  │ TimescaleDB  │
└──────────────────────────────────────────────────┘
```

### Internal Module Structure (Clean Architecture)
```
modules/<module_name>/
├── domain/          # Entities, value objects, domain events
├── application/     # Use cases, commands, queries, DTOs
├── infrastructure/  # Repositories, external adapters
└── presentation/    # API routers, request/response schemas
```

---

## Data Pipeline (Planned)

```
CERT Dataset / Log Sources
          │
          ▼
  Dataset Ingestion (Adapters)
          │
          ▼
   Raw Log Parser
          │
          ▼
  Canonical Event Schema
          │
          ▼
   Kafka / Message Queue
          │
          ▼
   Stream Processing
          │
          ▼
  Normalization & Enrichment
          │
          ▼
   Feature Extraction
          │
          ▼
    Feature Store
          │
    ┌─────┴──────┐
    ▼            ▼
Behavioral   Anomaly
Profiling    Detection
    │            │
    └─────┬──────┘
          ▼
    Risk Scoring
          │
          ▼
   UEBA Intelligence
          │
          ▼
   Alert Management
          │
          ▼
  Threat Investigation
          │
          ▼
   Response & Workflow
```

---

## Tech Stack

### Backend
| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Framework | FastAPI |
| ORM | SQLAlchemy (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | JWT (access + refresh) |
| Authorization | RBAC |

### Databases & Storage
| Store | Technology | Purpose |
|---|---|---|
| Relational | PostgreSQL 16 | Users, config, alerts, investigations |
| Document | MongoDB | Activity logs, enriched events |
| Search | Elasticsearch 8 | Fast log & alert querying |
| Cache | Redis 7 | Sessions, token blacklist, feature cache |
| Queue | Kafka | Activity event streaming |
| Object | MinIO | Evidence, reports, raw log archives |
| Time-Series | TimescaleDB | Behavioral metrics over time |

### Frontend
| Component | Technology |
|---|---|
| Framework | React 18 + TypeScript |
| Build Tool | Vite |
| Styling | Tailwind CSS |
| Routing | React Router v6 |
| Data Fetching | React Query (TanStack) |
| HTTP | Axios |
| Charts | Recharts |

---

## Quick Start

### Prerequisites

- Docker Desktop ≥ 4.x
- Docker Compose v2
- Node.js 20+
- Python 3.11+

### 1. Clone and Configure

```bash
git clone <repository-url>
cd project2
cp .env.example .env
# Edit .env with your values
```

### 2. Start Infrastructure Services

```bash
docker compose up -d
```

### 3. Start Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Verify Health

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready
```

Frontend: http://localhost:5173  
Backend API Docs: http://localhost:8000/docs  
Backend ReDoc: http://localhost:8000/redoc

---

## Project Structure

```
project2/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── core/               # Config, security, database connections
│   │   ├── modules/            # Feature modules (bounded contexts)
│   │   │   ├── identity/       # Auth, RBAC
│   │   │   ├── users/          # User management
│   │   │   ├── assets/         # Device/asset inventory
│   │   │   ├── activity/       # Log ingestion, events
│   │   │   ├── behavioral/     # Behavioral profiling
│   │   │   ├── anomaly/        # Anomaly detection
│   │   │   ├── risk/           # Risk scoring
│   │   │   ├── ueba/           # UEBA intelligence
│   │   │   ├── alerts/         # Alert management
│   │   │   ├── investigations/ # Threat investigation
│   │   │   ├── response/       # Response workflows
│   │   │   ├── reporting/      # Reports & analytics
│   │   │   ├── notifications/  # Notification delivery
│   │   │   └── admin/          # Administration
│   │   ├── shared/             # Shared utilities, base classes
│   │   └── main.py             # FastAPI application entry point
│   ├── alembic/                # Database migrations
│   ├── tests/                  # Test suite
│   └── requirements.txt
├── frontend/                   # React + TypeScript application
│   ├── src/
│   │   ├── components/         # Shared UI components
│   │   ├── pages/              # Route pages
│   │   ├── modules/            # Feature modules
│   │   ├── hooks/              # Custom React hooks
│   │   ├── services/           # API service layer
│   │   ├── store/              # State management
│   │   ├── types/              # TypeScript type definitions
│   │   └── utils/              # Utility functions
│   ├── public/
│   └── package.json
├── docs/                       # Project documentation
│   ├── architecture/           # Architecture decision records
│   ├── api/                    # API documentation
│   ├── data/                   # Data models, schemas
│   ├── ml/                     # ML pipeline documentation
│   ├── deployment/             # Deployment guides
│   └── assets/                 # Images, diagrams
├── data/                       # Datasets (gitignored)
│   ├── cert/                   # CERT dataset files
│   └── raw/                    # Other raw data
├── scripts/                    # Utility scripts
├── docker/                     # Docker configuration files
├── .env.example                # Environment variable template
├── docker-compose.yml          # Development infrastructure
├── PROJECT_RULES.md            # Project governance rules
└── README.md                   # This file
```

---

## Implementation Phases

| Phase | Status | Description |
|---|---|---|
| **Phase 0** | ✅ Complete | Project foundation, structure, Docker |
| **Phase 1** | ⏳ Pending | Identity & Access — Auth, RBAC |
| **Phase 2** | ⏳ Pending | User & Asset Management |
| **Phase 3** | ⏳ Pending | Activity Collection — Log ingestion |
| **Phase 4** | ⏳ Pending | CERT Dataset Adapter |
| **Phase 5** | ⏳ Pending | Behavioral Profiling |
| **Phase 6** | ⏳ Pending | Anomaly Detection (Isolation Forest) |
| **Phase 7** | ⏳ Pending | Risk Scoring Engine |
| **Phase 8** | ⏳ Pending | Alert Management |
| **Phase 9** | ⏳ Pending | UEBA Intelligence |
| **Phase 10** | ⏳ Pending | Threat Investigation |
| **Phase 11** | ⏳ Pending | SOC Dashboard |
| **Phase 12** | ⏳ Pending | Response & Reporting |

---

## Documentation Index

| Document | Path |
|---|---|
| Project Rules | [PROJECT_RULES.md](PROJECT_RULES.md) |
| Architecture Overview | [docs/architecture/overview.md](docs/architecture/overview.md) |
| ADR Index | [docs/architecture/decisions/](docs/architecture/decisions/) |
| API Reference | [docs/api/](docs/api/) |
| Data Models | [docs/data/](docs/data/) |
| ML Pipeline | [docs/ml/](docs/ml/) |
| Deployment Guide | [docs/deployment/](docs/deployment/) |

---

## Security Notice

This system processes sensitive employee behavioral data. Access is restricted to authorized security personnel. All activity within the system is audit-logged.

---

## License

Internal use only. All rights reserved.
