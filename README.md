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

## Key Capabilities

| Capability | Status | Description |
|---|---|---|
| 🔍 **Behavioral Profiling** | ✅ Implemented | Learns normal user behavior and peer-group patterns |
| 🤖 **Anomaly Detection** | ✅ Implemented | Isolation Forest + unsupervised ML for unknown threats |
| ⚠️ **Risk Scoring** | ✅ Implemented | Explainable composite insider risk scores |
| 🚨 **Alert Management** | ✅ Implemented | Deduplication, severity, routing, enrichment |
| 🔎 **Threat Investigation** | ✅ Implemented | Timeline, evidence collection, case management |
| 📊 **SOC Dashboard** | ✅ Implemented | Real-time analyst view of threats and investigations |
| 📋 **Response Workflows** | 📋 Planned | Playbooks, automation, SOAR integration |
| 📈 **Reporting** | ✅ Implemented | CSV export for alerts and investigations |

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

## Data Pipeline (Implemented)

> **Note:** Kafka, Elasticsearch, and MinIO are configured in Docker but not yet wired into the event pipeline.

```
CSV Files → Ingestion API → Parsers → MongoDB → Behavioral Features → ML Anomaly → Alerts → Investigations → SOC Dashboard
```

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
| **Phase 1** | ✅ Complete | Identity & Access — Auth, JWT, RBAC |
| **Phase 2** | ✅ Complete | Activity & Event Ingestion — CSV, parsers, canonical events |
| **Phase 3** | ✅ Complete | Windows Endpoint Agent — `agent/` directory |
| **Phase 4** | ✅ Complete | Behavioral Feature Engineering — 16 features, user baselines |
| **Phase 5** | ✅ Complete | ML Anomaly Detection — Isolation Forest, risk scoring |
| **Phase 6.1** | ✅ Complete | Alerts & Investigations — lifecycle, linking, notes |
| **Phase 6.2** | ✅ Complete | Frontend SOC Dashboard — React/Vite, real API integration |
| **Phase 6.3** | ✅ Complete | System Integration Audit — Full architecture review |
| **Phase 6.4** | ✅ Complete | Alert Generation Frontend — UI button |
| **Phase 6.5** | ✅ Complete | End-to-End Verification — All flows tested |
| **Phase 7** | 🔄 In Progress | Deployment, Documentation & Demo Readiness |
| **Phase 8+** | ⏳ Pending | Risk Module, Notifications, Reporting, Response Workflows |

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

## Demo Workflow

A step-by-step guide to demonstrate the full ITBIS detection pipeline.

### Prerequisites

1. Docker Desktop running with `docker compose up -d`
2. Backend running on `http://localhost:8000`
3. Frontend running on `http://localhost:5173`

### Default Credentials

| Role | Email | Password |
|------|-------|----------|
| Superadmin | `admin@itbis-platform.com` | `Admin@ITBIS1` |

---

### Step 1 — Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@itbis-platform.com", "password": "Admin@ITBIS1"}'
```

Or open http://localhost:5173 in your browser and login with the credentials above.

---

### Step 2 — Ingest Activity Data

The system ships with sample CERT-style activity data generators. Use the backend seeder or upload CSV data:

```bash
# Upload CERT-format CSV via the API
curl -X POST http://localhost:8000/api/v1/ingestion/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@data/cert/insider Threat/CERT/structured/2010-02.csv"
```

---

### Step 3 — Generate Behavioral Features

```bash
curl -X POST http://localhost:8000/api/v1/behavioral/generate \
  -H "Authorization: Bearer <token>"
```

This computes 16 behavioral features per user (login frequency, file access patterns, email activity, etc.) and builds user baselines.

---

### Step 4 — Run Anomaly Detection

```bash
curl -X POST http://localhost:8000/api/v1/anomaly/detect \
  -H "Authorization: Bearer <token>"
```

The Isolation Forest model scores each user against their behavioral baseline. High anomaly scores indicate potential insider threat behavior.

---

### Step 5 — Generate Alerts

```bash
curl -X POST http://localhost:8000/api/v1/alerts/generate \
  -H "Authorization: Bearer <token>"
```

Alert policies evaluate anomaly results and create security alerts for high-risk users.

---

### Step 6 — Investigate Alerts

1. Open http://localhost:5173/alerts in your browser
2. View alert severity, assigned user, and risk details
3. Click into an alert and acknowledge it
4. Assign to an analyst or create a linked investigation

Or via API:

```bash
# Acknowledge an alert
curl -X POST http://localhost:8000/api/v1/alerts/<alert_id>/acknowledge \
  -H "Authorization: Bearer <token>"

# Create an investigation
curl -X POST http://localhost:8000/api/v1/investigations/ \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "Investigate user anomalies", "alert_ids": ["<alert_id>"]}'
```

---

### Step 7 — Export Reports

```bash
# Export alerts as CSV
curl http://localhost:8000/api/v1/reports/alerts/export \
  -H "Authorization: Bearer <token>" \
  -o alerts_report.csv

# Export investigations as CSV
curl http://localhost:8000/api/v1/reports/investigations/export \
  -H "Authorization: Bearer <token>" \
  -o investigations_report.csv
```

---

### Architecture Diagram

```
┌──────────────────────────────────────────────────────┐
│  Windows Endpoint / CSV Upload                       │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│  FastAPI Backend (Port 8000)                         │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ identity │  │ activity │  │   behavioral     │  │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│       │              │                  │            │
│       │      ┌───────┴───────┐         │            │
│       │      ▼               ▼         ▼            │
│       │  MongoDB        PostgreSQL   PostgreSQL      │
│       │  (events)       (users,      (baselines)     │
│       │                  baselines)                   │
│       │                  │                           │
│       └────────┬─────────┘                           │
│                │                                     │
│       ┌────────▼────────┐                           │
│       │    anomaly      │                           │
│       │ (IsolationForest)│                          │
│       └────────┬────────┘                           │
│                │                                     │
│       ┌────────▼────────┐                           │
│       │     alerts      │                           │
│       └────────┬────────┘                           │
│                │                                     │
│       ┌────────▼────────┐                           │
│       │ investigations  │                           │
│       └─────────────────┘                           │
└────────────────────┬─────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │  React Frontend     │
          │  (Port 5173)       │
          │  SOC Dashboard      │
          └─────────────────────┘
```

---

## Security Notice

This system processes sensitive employee behavioral data. Access is restricted to authorized security personnel. All activity within the system is audit-logged.

---

## License

Internal use only. All rights reserved.
