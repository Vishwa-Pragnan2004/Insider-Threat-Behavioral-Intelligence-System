# ITBIS Windows Endpoint Agent

A lightweight, self-contained Windows service that collects security-relevant
activity from the host and ships it to the ITBIS server as `CanonicalEvent`
documents over HTTPS.

The agent is a **collector**, not a detection engine. All intelligence
(anomaly detection, risk scoring, alerting) remains server-side.

## Architecture

```
Windows Event Sources
        ↓
Collectors (Windows Security, Process, USB)
        ↓
Event Normalization → CanonicalEvent
        ↓
Local Persistent Queue (SQLite)
        ↓
Batching + HTTPS Upload (with retry / backoff)
        ↓
ITBIS Server  /api/v1/ingestion/events
        ↓
Canonical Events (MongoDB)
```

The agent is **independent of the FastAPI server implementation**. It carries
its own copy of the `CanonicalEvent` Pydantic schema and never imports from
`backend/app/*`.

## Install

```bash
pip install -e .[windows]   # production install on Windows
pip install -e .[dev]       # development install
```

## Run

```bash
# Using a config file
itbis-agent --config config.yaml

# Or environment variables (ITBIS_AGENT_*)
itbis-agent
```

## Configuration

See `config.example.yaml` for the full schema. The minimum required settings
are:

```yaml
agent:
  device_id: "WS-DEV-001"
  device_name: "Workstation 001"
  source_dataset: "win_endpoint"

server:
  base_url: "https://itbis.example.com"
  api_key: "REPLACE_ME"
  events_path: "/api/v1/ingestion/events"

queue:
  db_path: "C:\\ProgramData\\ITBIS\\agent.db"

upload:
  batch_size: 200
  flush_interval_seconds: 10
  max_retries: 6
```

## Testing

```bash
pytest tests/                  # full suite
pytest tests/unit/             # unit only
pytest tests/integration/      # integration only (uses a fake server)
```

The integration tests use `respx` to mock the HTTP transport and an in-memory
SQLite queue. They do **not** require a running ITBIS server or Windows.
