# ITBIS — Behavioral Features & Baselines

**Phase 4 — feature engineering & per-user baselines**

This document is the **single source of truth** for the feature schema
used by the ITBIS server-side pipeline and the future Kaggle training
notebook.  The exact same definitions, names, types, and ordering MUST be
used in both.

---

## Feature version

```
FEATURE_VERSION = "behavioral_features_v1"
```

Bump the version in `app/modules/behavioral/domain/enums.py` whenever any
feature is added, removed, or has its calculation semantics changed.
Production ML models must check the version they were trained on.

## Canonical event input

Features are derived from `CanonicalEvent` documents (see
`backend/app/shared/schemas/canonical_event.py`).  The pipeline accepts
events from any `source_dataset` (`"cert"`, `"win_endpoint"`, etc.).
A feature row can be scoped to one source or to `"all"`.

Required fields per event:

| Field | Used by features |
|---|---|
| `event_type` | All features (gates per-event matching) |
| `timestamp` (UTC) | `after_hours_activity_count`, `unique_active_hours`, daily bucketing |
| `user_id` | Group-by key for feature rows |
| `device_id` | `unique_device_count` |
| `target_resource` | `unique_resource_count` |
| `risk_indicators` | `external_email_count` |

Missing fields are tolerated; the affected features default to zero.

## Aggregation windows

| Window | Definition | Default |
|---|---|---|
| `daily` | One row per UTC day in `[start, end)`. | yes |
| `rolling_7d` | One row per day, value = features over the trailing 7 days ending at that day. | opt-in |
| `rolling_30d` | Same as above with a 30-day window. | opt-in |

A row carries the `window` name and the `[window_start, window_end)` it
covers.  All windows are UTC-aligned.

## Feature definitions (v1, 16 features)

For every feature: name, data type, calculation, and required fields.
Names are stable and ordered; the table is the wire contract.

| # | Name | Type | Calculation | Required input fields |
|---|---|---|---|---|
| 1 | `total_activity_count` | `int` | Count of all canonical events in the window. | `event_type` |
| 2 | `logon_count` | `int` | Count of `LOGON` events. | `event_type` |
| 3 | `failed_logon_count` | `int` | Count of `LOGON_FAILED` events. | `event_type` |
| 4 | `after_hours_activity_count` | `int` | Count of events with `timestamp.hour < 8 or >= 18` (UTC proxy for working hours). | `event_type`, `timestamp` |
| 5 | `unique_active_hours` | `int` | Distinct `timestamp.hour` values present in the window. | `event_type`, `timestamp` |
| 6 | `unique_device_count` | `int` | Distinct non-null `device_id` values. | `event_type`, `device_id` |
| 7 | `unique_resource_count` | `int` | Distinct non-null `target_resource` values. | `event_type`, `target_resource` |
| 8 | `file_activity_count` | `int` | Count of `file_*` events (`file_read`, `file_write`, `file_delete`, `file_copy`, `file_move`). | `event_type` |
| 9 | `file_copy_count` | `int` | Count of `file_copy` events. | `event_type` |
| 10 | `usb_activity_count` | `int` | Count of `usb_*` events (`usb_insert`, `usb_remove`, `usb_file_copy`). | `event_type` |
| 11 | `email_count` | `int` | Count of `email_*` events. | `event_type` |
| 12 | `external_email_count` | `int` | Count of `email_*` events with `event_type == "email_external"` OR `"external_email" in risk_indicators`. | `event_type`, `risk_indicators` |
| 13 | `http_activity_count` | `int` | Count of `http_*` events. | `event_type` |
| 14 | `ldap_activity_count` | `int` | Count of `ldap_query`, `privilege_change`, `group_change`, `account_created`, `account_disabled`, `password_change`. | `event_type` |
| 15 | `process_activity_count` | `int` | Count of `app_launch`, `app_close`, `app_install`. | `event_type` |
| 16 | `activity_type_diversity` | `int` | Distinct `event_type` values seen. | `event_type` |

## Feature row layout (storage)

Each feature row stored in MongoDB collection `behavioral_features`:

```json
{
  "_id":                "uuid",
  "user_id":            "alice",
  "window":             "daily",            // or "rolling_7d" / "rolling_30d"
  "window_start":       "2026-08-01T00:00:00+00:00",
  "window_end":         "2026-08-02T00:00:00+00:00",
  "source_dataset":     "cert",              // or "win_endpoint" / "all"
  "feature_version":    "behavioral_features_v1",
  "event_count":        47,
  "features": {
      "total_activity_count":     47.0,
      "logon_count":              3.0,
      "failed_logon_count":       0.0,
      "after_hours_activity_count": 1.0,
      "unique_active_hours":      4.0,
      "unique_device_count":      1.0,
      "unique_resource_count":    12.0,
      "file_activity_count":      2.0,
      "file_copy_count":          0.0,
      "usb_activity_count":       0.0,
      "email_count":              5.0,
      "external_email_count":     1.0,
      "http_activity_count":      15.0,
      "ldap_activity_count":      0.0,
      "process_activity_count":   4.0,
      "activity_type_diversity":  7.0
  },
  "generated_at":       "2026-08-30T12:00:00+00:00"
}
```

## Baseline schema (storage)

A baseline is per `(user_id, feature_version)` and is stored in Postgres
`behavioral_baselines`:

| Column | Type | Meaning |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | str | The user this baseline describes |
| `feature_version` | str | e.g. `"behavioral_features_v1"` |
| `stats` | JSONB | `{feature_name: {"mean", "std", "min", "max", "count"}}` |
| `window_start` | timestamptz | Historical observation start (inclusive) |
| `window_end` | timestamptz | Historical observation end (**exclusive** — also the start of the evaluation period) |
| `observation_days` | int | Number of days with non-zero activity |
| `source_dataset` | str | `"cert"` / `"win_endpoint"` / `"all"` |
| `created_at`, `updated_at` | timestamptz | Bookkeeping |

## Kaggle training pipeline — expected workflow

```python
# Inside the training notebook
from app.modules.behavioral.application.features import (
    FEATURE_DEFINITIONS,
    feature_names,
)
import pandas as pd
import pymongo

# 1. Pull feature rows from Mongo (use the same query the API uses)
client = pymongo.MongoClient("mongodb://...")
rows = list(client["itbis_events"]["behavioral_features"].find({
    "feature_version": "behavioral_features_v1",
    "source_dataset": "cert",
}))

# 2. Convert to a DataFrame, locking column order
df = pd.DataFrame([r["features"] for r in rows])
df = df[feature_names()].astype("float32")  # exact order
X = df.values

# 3. (Phase 5+) Train an unsupervised model on X
# model = IsolationForest().fit(X)
```

### Normalisation / scaling

Phase 4 produces **raw counts** (not normalised).  Scaling and
normalisation are the responsibility of the model-training phase.  Two
recommended approaches:

- **Standard scaler** fit on baseline stats (mean/std are already stored
  on `behavioral_baselines.stats`).
- **Log1p** for heavily-skewed counts (file / email / http) before
  scaling.

The two pipelines (training + inference) must apply the same
transformation.  Persist the fitted scaler alongside the model.

## Future-data leakage prevention

Baselines are built only over the historical window `[history_start, history_end)`.
The builder at `app/modules/behavioral/application/baseline.py` enforces
two guards:

1. A daily feature row is **rejected** if its `window_start >= history_end`.
2. A row is **rejected** if it straddles the boundary
   (`window_end > history_end`).

Tests: `tests/unit/behavioral/test_baseline.py::test_build_baseline_excludes_future_rows`,
`test_build_baseline_excludes_rows_outside_history`,
`test_build_baseline_partial_overlap_uses_capped_window`,
and `tests/unit/behavioral/test_service.py::test_build_baseline_excludes_evaluation_period`.

## Adding new features

1. Add a `FeatureDefinition` entry in
   `app/modules/behavioral/application/features.py` (with the per-event
   classifier function for `event_match` features, or the field name for
   `set_size` features).
2. Add the new name to `FEATURE_NAMES` in
   `app/modules/behavioral/domain/enums.py` in the right position
   (column order matters).
3. Bump `FEATURE_VERSION` to `behavioral_features_v2`.
4. Add unit tests in `tests/unit/behavioral/test_features.py` and
   `test_aggregator.py`.
5. Re-run the full test suite.

---

## Phase 5 — Training Dataset Export

`app/modules/behavioral/application/training_export.py` provides a
deterministic, leakage-safe exporter that reads existing Phase 4
`BehavioralFeatures` rows and produces:

| File | Format | Purpose |
|---|---|---|
| `<output_dir>/features.csv` | CSV | ML-ready matrix.  Metadata columns first, then the locked `FEATURE_NAMES` in fixed order, sorted by `(user_id, window, window_start)`. |
| `<output_dir>/manifest.json` | JSON | Provenance, column order, feature schema, contract guarantees. |

### Contract guarantees (enforced by tests in `tests/unit/behavioral/test_training_export.py`)

1. **Column order is locked** to `metadata + FEATURE_NAMES` from
   `app/modules.behavioral.domain.enums`.  The exporter asserts this
   on every row.
2. **`feature_version` lock** — every emitted row's `feature_version`
   must equal the requested `FEATURE_VERSION`.  Mismatches surface as
   `ExportResult.warnings` (the row is still emitted so the operator
   can decide what to do).
3. **Leakage guards** — rows are dropped if:
   - `window_start < request.start`
   - `window_end > request.end` (rows that straddle the upper boundary)
4. **Missing values are filled with `0.0`**.  No `NaN` ever appears in
   the CSV.
5. **Deterministic output** — given the same input rows and the same
   request, the produced CSV is byte-identical (rows sorted, float
   representation stable, manifest sorted by JSON keys).
6. **No user_id leakage** — `user_id` is a **metadata** column (so
   Kaggle can join labels) but is **not** an ML feature.

### CSV column layout

```
# features.csv
user_id, window, window_start, window_end, source_dataset,
feature_version, event_count,
total_activity_count, logon_count, failed_logon_count,
after_hours_activity_count, unique_active_hours,
unique_device_count, unique_resource_count,
file_activity_count, file_copy_count,
usb_activity_count,
email_count, external_email_count,
http_activity_count, ldap_activity_count,
process_activity_count, activity_type_diversity
```

The first 7 columns are metadata; the remaining 16 are the locked ML
feature vector in `FEATURE_NAMES` order.

### Manifest shape (excerpt)

```json
{
  "schema_version": 1,
  "feature_version": "behavioral_features_v1",
  "generated_at": "2026-08-30T12:00:00+00:00",
  "request": {
    "start": "2026-08-01T00:00:00+00:00",
    "end":   "2026-08-31T00:00:00+00:00",
    "source_dataset": "cert",
    "window": "daily"
  },
  "row_count": 12345,
  "column_order": ["user_id", "..."],
  "metadata_columns": ["user_id", "window", "..."],
  "ml_feature_columns": ["total_activity_count", "..."],
  "feature_schema": [
    {"name": "total_activity_count", "aggregator": "count",
     "description": "Total count of canonical events in the window."},
    "..."
  ],
  "missing_value_policy": "filled_with_zero",
  "deterministic": true,
  "row_sort_order": ["user_id", "window", "window_start"],
  "leakage_guards": [
    "row_rejected_if_window_start_lt_request_start",
    "row_rejected_if_window_end_gt_request_end",
    "feature_version_must_equal_request.feature_version"
  ],
  "intended_consumers": [
    "kaggle_training_notebook",
    "itbis_production_inference"
  ]
}
```

### Kaggle notebook — recommended workflow

```python
# 1. Download the export artefacts from the ITBIS server
#    (use POST /api/v1/behavioral/export to produce them)

# 2. Load the manifest to discover the locked column order
import json, pandas as pd
manifest = json.load(open("manifest.json"))
column_order = manifest["ml_feature_columns"]  # 16 names, locked

# 3. Load the CSV and split metadata from the matrix
df = pd.read_csv("features.csv")
meta = df[manifest["metadata_columns"]]
X   = df[column_order].astype("float32")        # locked order

# 4. (CERT) Load the published insider-threat labels and join on
#    (user_id, window, window_start) — meta is the join key
labels = pd.read_csv("/kaggle/input/cert/labels.csv")
y = labels.set_index(["user_id", "window_start"]).loc[
    list(zip(meta["user_id"], meta["window_start"]))
]["is_insider"]

# 5. Train the model (Phase 5+)
# from sklearn.ensemble import IsolationForest
# model = IsolationForest().fit(X.values)
```

### ITBIS production inference contract

The same `FEATURE_NAMES` order is used at inference time:

1. Build the live feature row for a `(user_id, window, window_start)`
   using the same Phase 4 service.
2. Project it through the same scaler that was fit during training
   (the manifest will include the scaler hash in a later phase).
3. Call `model.predict([X])` with the 16-column vector in the locked
   order.

Any drift between the training and inference feature version MUST be
detected at startup — `behavioral_features_v1` is a hard contract.
