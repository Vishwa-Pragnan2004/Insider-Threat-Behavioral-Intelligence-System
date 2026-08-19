# ITBIS — Canonical Event Schema

The **Canonical Event Schema** is the normalised event representation that all log sources must produce after ingestion and parsing.

No raw log data ever enters the ML pipeline or feature store. Everything must first be converted to this schema.

## Purpose

- Provides a **single source of truth** for all events regardless of origin
- Decouples the ingestion layer from the processing pipeline
- Allows adding new log sources without modifying downstream components

## Schema Fields

### Identity
| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | UUID | ✅ | Unique ITBIS event identifier |
| `event_type` | Enum | ✅ | Canonical event type |
| `source_dataset` | string | ✅ | Source name, e.g. `cert_r4.2` |
| `raw_event_id` | string | ❌ | Original ID from source log |

### Timing
| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | datetime (UTC) | ✅ | When the event occurred |
| `ingested_at` | datetime (UTC) | ✅ | When ITBIS ingested it |

### Actor
| Field | Type | Required | Description |
|---|---|---|---|
| `user_id` | string | ✅ | Internal ITBIS user ID |
| `username` | string | ❌ | Username / login name |
| `user_email` | string | ❌ | User email address |
| `employee_id` | string | ❌ | HR employee ID |
| `department` | string | ❌ | Department name |

### Asset / Device
| Field | Type | Required | Description |
|---|---|---|---|
| `device_id` | string | ❌ | Internal device ID |
| `device_name` | string | ❌ | Hostname or device name |
| `ip_address` | string | ❌ | Source IP address |
| `mac_address` | string | ❌ | MAC address |
| `operating_system` | string | ❌ | OS name |

### Activity
| Field | Type | Required | Description |
|---|---|---|---|
| `target_resource` | string | ❌ | File path, URL, email, etc. |
| `target_type` | string | ❌ | `file`, `url`, `email`, etc. |
| `action` | string | ❌ | Action performed |
| `result` | string | ❌ | `success`, `failure`, `blocked` |
| `bytes_transferred` | int | ❌ | Data size in bytes |
| `file_count` | int | ❌ | Number of files |

### Risk
| Field | Type | Required | Description |
|---|---|---|---|
| `risk_indicators` | string[] | ❌ | Applied risk flags |
| `risk_score` | float | ❌ | Computed risk score |
| `risk_level` | Enum | ❌ | `info/low/medium/high/critical` |

## Canonical Event Types

See `app/shared/schemas/canonical_event.py` for the full `EventType` enum.

Key types:
- Authentication: `logon`, `logoff`, `logon_failed`
- File: `file_read`, `file_write`, `file_copy`, `file_download`, `file_upload`
- USB: `usb_insert`, `usb_remove`, `usb_file_copy`
- Email: `email_sent`, `email_external`
- Web: `http_request`, `http_upload`
- LDAP/AD: `privilege_change`, `group_change`
- Network: `vpn_connect`, `data_transfer`
