"""
ITBIS — API v1 Router
Aggregates all module routers under /api/v1/
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health

api_v1_router = APIRouter()

# ─── Health ─────────────────────────────────────────────────
api_v1_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health"],
)

from app.modules.identity.presentation.router import router as identity_router
from app.modules.activity.presentation.router import router as activity_router
from app.modules.activity.presentation.agent_router import router as agent_router
from app.modules.behavioral.presentation.router import router as behavioral_router
from app.modules.anomaly.presentation.router import router as anomaly_router
from app.modules.alerts.presentation.router import router as alerts_router
from app.modules.investigations.presentation.router import (
    router as investigations_router,
)
from app.modules.reporting.presentation.router import router as reporting_router
# from app.modules.users.presentation import router as users_router
api_v1_router.include_router(identity_router, prefix="/auth", tags=["Identity"])
api_v1_router.include_router(activity_router, prefix="/ingestion", tags=["Activity"])
api_v1_router.include_router(agent_router, prefix="/ingestion", tags=["Activity-Agent"])
api_v1_router.include_router(behavioral_router, prefix="/behavioral", tags=["Behavioral"])
api_v1_router.include_router(anomaly_router, prefix="/anomaly", tags=["Anomaly"])
api_v1_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_v1_router.include_router(
    investigations_router, prefix="/investigations", tags=["Investigations"]
)
api_v1_router.include_router(reporting_router, prefix="/reports", tags=["Reports"])
# api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])
# api_v1_router.include_router(activity_router, prefix="/activity", tags=["Activity"])
