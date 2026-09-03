"""
ITBIS — Behavioral Module: Pydantic API Schemas
"""


from app.modules.behavioral.application.dtos import (
    BehavioralFeatureListResponse,
    BehavioralFeatureRow,
    BehavioralProfileResponse,
    FeatureGenerationRequest,
    FeatureGenerationResponse,
    TrainingExportRequest,
    TrainingExportResponse,
)

# Resolve forward references
BehavioralFeatureListResponse.model_rebuild()
BehavioralFeatureRow.model_rebuild()
BehavioralProfileResponse.model_rebuild()
FeatureGenerationRequest.model_rebuild()
FeatureGenerationResponse.model_rebuild()
TrainingExportRequest.model_rebuild()
TrainingExportResponse.model_rebuild()
