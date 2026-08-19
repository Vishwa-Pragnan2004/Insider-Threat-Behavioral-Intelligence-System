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
# from app.modules.users.presentation import router as users_router
# from app.modules.activity.presentation import router as activity_router
# from app.modules.alerts.presentation import router as alerts_router
api_v1_router.include_router(identity_router, prefix="/auth", tags=["Identity"])
# api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])
# api_v1_router.include_router(activity_router, prefix="/activity", tags=["Activity"])
# api_v1_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
