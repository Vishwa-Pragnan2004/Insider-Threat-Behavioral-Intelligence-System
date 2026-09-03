"""
ITBIS — Anomaly Module: Pydantic API Schemas (re-exports + model_rebuild)
"""
from app.modules.anomaly.application.dtos import (
    AnomalyDetectRequest,
    AnomalyDetectResponse,
    AnomalyResultListResponse,
    AnomalyResultResponse,
    BehavioralDeviationResponse,
    ModelInfoResponse,
)

# Pydantic forward-reference resolution (no forward refs in this file,
# but call model_rebuild for safety with Pydantic v2 strict mode).
AnomalyDetectRequest.model_rebuild()
AnomalyDetectResponse.model_rebuild()
AnomalyResultResponse.model_rebuild()
AnomalyResultListResponse.model_rebuild()
BehavioralDeviationResponse.model_rebuild()
ModelInfoResponse.model_rebuild()
