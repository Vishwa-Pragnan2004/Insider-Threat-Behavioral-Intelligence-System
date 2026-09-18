# ITBIS - Insider Threat Behavioral Intelligence System

## Project Report
**Date:** September 5, 2026  
**Project:** Insider Threat Behavioral Intelligence System (ITBIS)

---

## 1. Executive Summary

ITBIS is a full-stack insider threat detection platform that monitors employee activity through endpoint agents, analyzes behavioral patterns using machine learning, and provides security analysts with tools to investigate anomalies and generate reports.

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐     ┌─────────────────┐
│ Windows Endpoint │     │              ITBIS Server                   │     │   Dashboard      │
│    Agent        │────▶│  POST /api/v1/ingestion/events           │     │   (React)      │
│ (client logs)   │     │                                          │     │                 │
└─────────────────┘     │  ┌─────────────┐    ┌───────────────┐   │     │  - Alerts      │
                         │  │  MongoDB    │───▶│  Behavioral   │   │     │  - Investigate │
                         │  │  (events)   │    │  Feature      │   │     │  - Reports    │
                         │  └─────────────┘    │  Extraction   │   │     │                 │
                         │                    │  (32 features)│   │     └─────────────────┘
                         │                    └──────┬───────┘   │
                         │                           ▼           │
                         │                    ┌───────────────┐   │
                         │                    │  Isolation    │   │
                         │                    │  Forest       │   │
                         │                    │  (ML Model)  │   │
                         │                    └──────┬───────┘   │
                         │                           ▼           │
                         │                    ┌───────────────┐   │
                         │                    │   Alerts      │   │
                         │                    │   PostgreSQL  │   │
                         │                    └───────────────┘   │
                         └──────────────────────────────────┘
```

### 2.2 Technology Stack

| Component | Technology |
|-----------|------------|
| **Backend** | FastAPI (Python 3.12) |
| **Database** | PostgreSQL 5434 (Docker) |
| **Event Store** | MongoDB (for activity events) |
| **ML Framework** | Scikit-learn (Isolation Forest) |
| **Frontend** | React 18 + Vite + TypeScript |
| **UI Library** | Material UI (MUI) |
| **State Management** | React Query (TanStack Query) |
| **Charts** | Recharts |
| **Authentication** | JWT tokens (access + refresh) |
| **Password Hashing** | bcrypt |

---

## 3. Functional Components

### 3.1 Data Ingestion Module

**Endpoint:** `POST /api/v1/ingestion/events`

**Purpose:** Receives normalized activity events from endpoint agents.

**Supported Event Types:**
- `LOGON` - User login/logout events
- `DEVICE` - USB/device connection events
- `FILE` - File access/copy events
- `EMAIL` - Email sent/received events
- `HTTP` - Web browsing activity
- `LDAP` - Directory service queries
- `PROCESS` - Process execution

**Request Schema:**
```json
{
  "agent_id": "string",
  "submitted_at": "datetime (optional)",
  "events": [
    {
      "event_type": "LOGON",
      "timestamp": "datetime",
      "user_id": "string",
      "pc": "string",
      "activity": "string",
      "raw_event_id": "string (optional)"
    }
  ]
}
```

### 3.2 Behavioral Feature Extraction

**Purpose:** Converts raw events into 32-dimensional behavioral feature vectors per user per time window.

**Features Extracted:**
| Feature | Description |
|---------|-------------|
| `total_activity_count` | Total events in window |
| `logon_count` | Number of logon events |
| `failed_logon_count` | Failed authentication attempts |
| `after_hours_activity_count` | Activity outside 8AM-6PM |
| `unique_active_hours` | Distinct hours with activity |
| `file_activity_count` | File operations |
| `file_copy_count` | File copy operations |
| `usb_activity_count` | USB device events |
| `email_count` | Email events |
| `external_email_count` | Emails to external domains |
| `http_activity_count` | Web requests |
| `ldap_activity_count` | Directory queries |
| `process_activity_count` | Process executions |
| `activity_type_diversity` | Number of distinct event types |

### 3.3 Anomaly Detection

**Algorithm:** Isolation Forest

**Configuration:**
- `contamination`: 0.05 (5% outliers expected)
- `anomaly_score_threshold`: 0.7

**Process:**
1. Features normalized using baseline statistics
2. Isolation Forest predicts `NORMAL` or `ANOMALY`
3. Anomaly score calculated from prediction path length
4. Risk score derived from score and feature deviations

### 3.4 Alert Generation

**Alert Policy:**
- `prediction` must equal `ANOMALY`
- Alert severity derived from risk score:
  - `CRITICAL`: score >= 0.9
  - `HIGH`: score >= 0.8
  - `MEDIUM`: score >= 0.7
  - `LOW`: score < 0.7

**Alert Attributes:**
- `severity` (CRITICAL/HIGH/MEDIUM/LOW)
- `risk_score` (0.0 - 1.0)
- `title` / `description`
- `user_id`
- `top_behavioral_deviations` (top 5 anomalous features)
- `window` / `window_start` / `window_end`

### 3.5 Investigation Workflow

**Status Flow:**
```
OPEN → ACKNOWLEDGED → IN_PROGRESS → RESOLVED / FALSE_POSITIVE
```

**Features:**
- Create investigations linked to alerts
- Add investigation notes with timestamps
- Link multiple alerts to one investigation
- Assign investigators
- Track resolution

### 3.6 Reporting

**CSV Export:** `GET /api/v1/reports/alerts/export`

**Exported Fields:**
- Alert ID, Severity, Status
- User ID
- Title, Description
- Risk Score
- Behavioral Deviations
- Time Window
- Investigation ID (if linked)
- Created At

---

## 4. User Authentication & Authorization

### 4.1 Roles & Permissions

| Role | Permissions |
|------|-------------|
| `ADMIN` | Full system access (19 permissions) |
| `SECURITY_ANALYST` | Alerts + Investigations (15 permissions) |
| `INVESTIGATOR` | Investigation management (8 permissions) |
| `VIEWER` | Read-only access (6 permissions) |

### 4.2 Default Admin Credentials

**Email:** `admin@itbis-platform.com`  
**Password:** `Admin@ITBIS1`

### 4.3 Auth Audit Logging

**Events Logged:**
- `LOGIN_SUCCESS` - Successful authentication
- `LOGIN_FAILURE` - Failed login attempts
- `LOGOUT` - User logout
- `TOKEN_REFRESH` - Token renewal
- `REGISTER` - New user registration

**Logged Data:**
- Event type
- Timestamp
- User ID (when applicable)
- Username
- IP address
- User agent (device info)
- Success/failure status
- Failure reason (when applicable)

**Note:** Currently logs to backend stdout only. Database persistence pending.

---

## 5. API Endpoints

### 5.1 Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Login with email/password |
| POST | `/api/v1/auth/logout` | Logout (revoke refresh token) |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Get current user profile |
| PATCH | `/api/v1/auth/me` | Update current user profile |

### 5.2 Activity Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ingestion/events` | Batch ingest from agent |
| POST | `/api/v1/ingestion/upload` | File-based CSV upload |

### 5.3 Anomaly Detection

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/anomaly/detect` | Run anomaly detection on features |
| POST | `/api/v1/anomaly/train` | Retrain ML model |

### 5.4 Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/alerts` | List alerts with filters |
| GET | `/api/v1/alerts/{id}` | Get alert details |
| POST | `/api/v1/alerts/{id}/acknowledge` | Acknowledge alert |
| PATCH | `/api/v1/alerts/{id}/status` | Update alert status |
| POST | `/api/v1/alerts/generate` | Generate alerts from features |

### 5.5 Investigations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/investigations` | List investigations |
| GET | `/api/v1/investigations/{id}` | Get investigation details |
| POST | `/api/v1/investigations` | Create investigation |
| PATCH | `/api/v1/investigations/{id}/status` | Update status |
| POST | `/api/v1/investigations/{id}/assign` | Assign investigator |
| POST | `/api/v1/investigations/{id}/notes` | Add note |
| GET | `/api/v1/investigations/{id}/notes` | List notes |
| POST | `/api/v1/investigations/{id}/link-alert` | Link alert |
| DELETE | `/api/v1/investigations/{id}/unlink-alert` | Unlink alert |

### 5.6 Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/reports/alerts/export` | Export alerts as CSV |

---

## 6. Database Schema

### 6.1 PostgreSQL Tables

```
app.users              - User accounts
app.roles             - Role definitions
app.permissions       - Permission definitions
app.user_roles        - User-role associations
app.role_permissions  - Role-permission associations
app.auth_audit_log    - Authentication audit trail
app.behavioral_baselines - Per-user baseline statistics
app.alerts            - Generated alerts
app.investigations    - Security investigations
app.investigation_notes - Investigation notes
app.ingestion_jobs    - Data ingestion job records
app.ingestion_errors  - Per-row ingestion failures
app.alembic_version   - Migration tracking
```

### 6.2 MongoDB Collections

```
canonical_events - Raw activity events from agents
```

---

## 7. Demo Pipeline

**Script:** `scripts/run_demo.py`

**Purpose:** Automated end-to-end demonstration of the detection pipeline.

**Steps:**
1. **Behavioral Generate** - Creates synthetic activity data for demo users
2. **Anomaly Detect** - Runs Isolation Forest on behavioral features
3. **Alerts Generate** - Creates alerts for detected anomalies
4. **Investigate** - Creates test investigations
5. **Reports Export** - Exports CSV report

**Usage:**
```bash
cd backend
POSTGRES_PORT=5434 python scripts/run_demo.py
```

---

## 8. Frontend Application

### 8.1 Pages

| Page | Route | Description |
|------|-------|-------------|
| Login | `/login` | Authentication page |
| Dashboard | `/dashboard` | KPI overview with charts |
| Alerts | `/alerts` | Alert list with filters |
| Alert Detail | Drawer | Alert details + actions |
| Investigations | `/investigations` | Investigation list |
| Investigation Detail | `/investigations/:id` | Full investigation view |
| Reports | `/reports` | Report generation |

### 8.2 Running the Application

**Backend:**
```bash
cd backend
POSTGRES_PORT=5434 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Access:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## 9. Known Issues & Limitations

### 9.1 Auth Audit Logging
- **Issue:** Authentication events only log to backend stdout
- **Impact:** No persistent audit trail for compliance
- **Fix Needed:** Implement database persistence in `AuditService`

### 9.2 Endpoint Agent
- **Issue:** No actual Windows endpoint agent software built
- **Impact:** Demo relies on synthetic data generator
- **Fix Needed:** Build Windows service that collects and sends logs

### 9.3 Demo Data Generation
- **Issue:** Synthetic anomalies may not trigger alerts consistently
- **Impact:** Alert generation may show 0 new alerts
- **Fix Needed:** Increase anomaly severity in demo data generator

### 9.4 Vite Optimization
- **Issue:** First load may take 2-3 minutes due to MUI icon bundling
- **Impact:** Slow initial page load for developers
- **Mitigation:** Subsequent loads are instant (cached)

---

## 10. Testing

### 10.1 Test Results

| Suite | Passed | Failed | Errors |
|-------|--------|--------|--------|
| Alerts Tests | 102 | 0 | 0 |
| Investigations Tests | 102 | 0 | 0 |
| Backend Full Suite | 433 | 13 | 25 |

### 10.2 Running Tests

```bash
cd backend
pytest tests/ -v
```

---

## 11. Future Enhancements

1. **Endpoint Agent Software** - Windows service for real-time log collection
2. **Auth Audit Persistence** - Store audit logs in PostgreSQL
3. **Dashboard Widgets** - Customizable dashboard
4. **Email Notifications** - Alert notifications via email
5. **Kafka Integration** - Event streaming for scalability
6. **Redis Caching** - Session and data caching
7. **Elasticsearch** - Advanced log search and analytics

---

## 12. Project Structure

```
project2/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── modules/
│   │   │   ├── activity/       # Data ingestion
│   │   │   ├── anomaly/        # ML detection
│   │   │   ├── identity/       # Auth & users
│   │   │   ├── alerts/         # Alert management
│   │   │   ├── investigations/  # Investigation workflow
│   │   │   └── reporting/       # Report generation
│   │   └── shared/
│   ├── alembic/versions/       # DB migrations
│   ├── scripts/
│   │   └── run_demo.py         # Demo pipeline
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   ├── services/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
└── README.md
```

---

## 13. Conclusion

ITBIS provides a complete insider threat detection platform with:
- Scalable event ingestion architecture
- ML-based behavioral anomaly detection
- Comprehensive investigation workflow
- Professional security operations dashboard

The core detection pipeline is functional and tested. The main gaps are the lack of a production endpoint agent and audit log persistence, both of which can be addressed in future development phases.
