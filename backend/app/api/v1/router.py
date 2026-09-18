"""
ITBIS — API v1 Router
Aggregates all module routers under /api/v1/
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health
from app.modules.activity.presentation.agent_router import router as agent_router
from app.modules.activity.presentation.events_router import router as events_router
from app.modules.activity.presentation.router import router as activity_router
from app.modules.alerts.presentation.router import router as alerts_router
from app.modules.anomaly.presentation.router import router as anomaly_router
from app.modules.behavioral.presentation.router import router as behavioral_router
from app.modules.dashboards.presentation.router import router as dashboards_router
from app.modules.employees.presentation.router import router as employees_router
from app.modules.feedback.presentation.router import router as feedback_router
from app.modules.identity.presentation.agent_router import (
    router as agent_devices_router,
)
from app.modules.identity.presentation.router import router as identity_router
from app.modules.investigations.presentation.router import (
    router as investigations_router,
)
from app.modules.reporting.presentation.router import router as reporting_router
from app.modules.risk.presentation.router import detections_router, risk_router
from app.modules.ueba.presentation.router import router as ueba_router
from app.modules.users.presentation.access_requests_router import (
    admin_router as access_requests_admin_router,
)
from app.modules.users.presentation.access_requests_router import (
    public_router as access_requests_public_router,
)
from app.modules.users.presentation.router import router as users_router

api_v1_router = APIRouter()

# ─── Health ─────────────────────────────────────────────────
api_v1_router.include_router(health.router, prefix="/health", tags=["Health"])

# ─── Identity & agent enrollment ────────────────────────────
api_v1_router.include_router(identity_router, prefix="/auth", tags=["Identity"])
api_v1_router.include_router(
    agent_devices_router, prefix="/agents", tags=["Agent Devices"]
)
api_v1_router.include_router(
    access_requests_public_router, prefix="/auth", tags=["Access Requests"]
)
# Before the users router: its /{user_id} route would capture /access-requests.
api_v1_router.include_router(
    access_requests_admin_router, prefix="/users", tags=["Access Requests"]
)
api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])
api_v1_router.include_router(employees_router, prefix="/employees", tags=["Employees"])

# ─── Ingestion ──────────────────────────────────────────────
api_v1_router.include_router(activity_router, prefix="/ingestion", tags=["Activity"])
api_v1_router.include_router(agent_router, prefix="/ingestion", tags=["Activity-Agent"])
api_v1_router.include_router(events_router, prefix="/activity", tags=["Activity"])

# ─── Analytics pipeline ─────────────────────────────────────
api_v1_router.include_router(
    behavioral_router, prefix="/behavioral", tags=["Behavioral"]
)
api_v1_router.include_router(anomaly_router, prefix="/anomaly", tags=["Anomaly"])

# ─── SOC workflow ───────────────────────────────────────────
api_v1_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_v1_router.include_router(
    investigations_router, prefix="/investigations", tags=["Investigations"]
)
api_v1_router.include_router(reporting_router, prefix="/reports", tags=["Reports"])
api_v1_router.include_router(feedback_router, prefix="/feedback", tags=["Analyst Feedback"])
api_v1_router.include_router(
    dashboards_router, prefix="/dashboards", tags=["Dashboards"]
)

# --- Continuous detection pipeline ---------------------------------------
api_v1_router.include_router(ueba_router, prefix="/ueba", tags=["UEBA"])

# --- Anomaly detection engine and insider risk scoring ------------------
api_v1_router.include_router(detections_router, prefix="/detections", tags=["Detections"])
api_v1_router.include_router(risk_router, prefix="/risk", tags=["Insider Risk"])

# Modules below are scaffolded but not yet implemented; their routers will be
# mounted here as each is built out (see PROJECT_RULES.md §6).
#   assets, risk, response, notifications, admin
