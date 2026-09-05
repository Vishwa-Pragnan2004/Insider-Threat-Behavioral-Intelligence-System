"""
ITBIS — Investigations Module: API Router

Endpoints (all under /api/v1/investigations):

  POST  /                          create investigation
  GET   /                          list investigations (paginated, filterable)
  GET   /{id}                      get full investigation
  POST  /{id}/assign               assign investigator
  POST  /{id}/status               change lifecycle status
  POST  /{id}/alerts               link an alert to the investigation
  DELETE /{id}/alerts/{alert_id}   unlink an alert
  POST  /{id}/notes                add a (immutable) note
  GET   /{id}/notes                list notes (chronological)

Permission map (re-uses Phase 1 RBAC):
  investigations:read     -> GET    endpoints
  investigations:create   -> POST   /, /{id}/alerts, /{id}/notes
  investigations:update   -> POST   /{id}/assign, /{id}/status
                             DELETE /{id}/alerts/{alert_id}
"""
# ruff: noqa: B008
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.alerts.domain.repositories import IAlertLinker
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)
from app.modules.investigations.application.dtos import (
    InvestigationAddAlertRequest,
    InvestigationAssignRequest,
    InvestigationCreateRequest,
    InvestigationListResponse,
    InvestigationResponse,
    InvestigationStatusRequest,
    NoteCreateRequest,
    NoteListResponse,
    NoteResponse,
)
from app.modules.investigations.application.investigation_service import (
    InvestigationService,
)
from app.modules.investigations.domain.enums import InvestigationStatus
from app.modules.investigations.domain.exceptions import (
    AssigneeNotFoundError,
    IllegalInvestigationStatusTransitionError,
    InvestigationNotFoundError,
)
from app.modules.investigations.presentation.dependencies import (
    get_alert_linker,
    get_investigation_service,
)

log = structlog.get_logger(__name__)

router = APIRouter()


# ─── DTO helpers ───────────────────────────────────────────


def _to_response(inv) -> InvestigationResponse:
    return InvestigationResponse(
        id=str(inv.id),
        title=inv.title,
        description=inv.description,
        severity=inv.severity,
        status=inv.status.value,
        created_by=inv.created_by,
        assigned_to=inv.assigned_to,
        related_alert_ids=[str(a) for a in inv.related_alert_ids],
        related_user_ids=list(inv.related_user_ids),
        resolution=inv.resolution,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        closed_at=inv.closed_at,
    )


def _note_to_response(n) -> NoteResponse:
    return NoteResponse(
        id=str(n.id),
        investigation_id=str(n.investigation_id),
        author_id=n.author_id,
        content=n.content,
        created_at=n.created_at,
    )


# ─── Endpoints ────────────────────────────────────────────


@router.post(
    "/",
    response_model=InvestigationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new investigation (optionally linked to alerts/users)",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_CREATE))],
)
async def create_investigation(
    body: InvestigationCreateRequest,
    current_user: User = Depends(require_active_user),
    service: InvestigationService = Depends(get_investigation_service),
):
    inv = await service.create(
        title=body.title,
        description=body.description,
        severity=body.severity,
        created_by=str(current_user.id),
        related_alert_ids=body.related_alert_ids,
        related_user_ids=body.related_user_ids,
        assigned_to=body.assigned_to,
    )
    return _to_response(inv)


@router.get(
    "/",
    response_model=InvestigationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List investigations with optional filters and pagination",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_READ))],
)
async def list_investigations(
    status_filter: InvestigationStatus | None = Query(None, alias="status"),
    assigned_to: str | None = Query(None),
    severity: str | None = Query(None),
    related_user_id: str | None = Query(None),
    created_by: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    service: InvestigationService = Depends(get_investigation_service),
):
    items, total = await service.list(
        status=status_filter,
        assigned_to=assigned_to,
        severity=severity,
        related_user_id=related_user_id,
        created_by=created_by,
        skip=skip,
        limit=limit,
    )
    return InvestigationListResponse(
        investigations=[_to_response(i) for i in items],
        count=len(items),
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{investigation_id}",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a single investigation",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_READ))],
)
async def get_investigation(
    investigation_id: uuid.UUID,
    service: InvestigationService = Depends(get_investigation_service),
):
    try:
        inv = await service.get(investigation_id)
        notes = await service.list_notes(investigation_id)
        response = _to_response(inv)
        response.notes = [_note_to_response(n) for n in notes]
        return response
    except InvestigationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/{investigation_id}/assign",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign an investigator",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_UPDATE))],
)
async def assign_investigation(
    investigation_id: uuid.UUID,
    body: InvestigationAssignRequest,
    service: InvestigationService = Depends(get_investigation_service),
):
    try:
        return _to_response(await service.assign(investigation_id, body.user_id))
    except InvestigationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except AssigneeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/{investigation_id}/status",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
    summary="Change investigation status (validates lifecycle transitions)",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_UPDATE))],
)
async def change_investigation_status(
    investigation_id: uuid.UUID,
    body: InvestigationStatusRequest,
    service: InvestigationService = Depends(get_investigation_service),
):
    try:
        new_status = InvestigationStatus(body.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown status: {body.status!r}",
        ) from exc
    try:
        return _to_response(
            await service.change_status(
                investigation_id, new_status, resolution=body.resolution
            )
        )
    except InvestigationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except IllegalInvestigationStatusTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post(
    "/{investigation_id}/alerts",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
    summary="Link an alert to an investigation (two-sided consistency)",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_CREATE))],
)
async def link_alert(
    investigation_id: uuid.UUID,
    body: InvestigationAddAlertRequest,
    service: InvestigationService = Depends(get_investigation_service),
    alert_service: IAlertLinker = Depends(get_alert_linker),
):
    try:
        inv = await service.add_alert(
            investigation_id=investigation_id,
            alert_id=body.alert_id,
            user_id=body.user_id,
            alert_service=alert_service,  # two-sided consistency
        )
    except InvestigationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _to_response(inv)


@router.delete(
    "/{investigation_id}/alerts/{alert_id}",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
    summary="Unlink an alert from an investigation (two-sided consistency)",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_UPDATE))],
)
async def unlink_alert(
    investigation_id: uuid.UUID,
    alert_id: uuid.UUID,
    service: InvestigationService = Depends(get_investigation_service),
    alert_service: IAlertLinker = Depends(get_alert_linker),
):
    try:
        return _to_response(
            await service.remove_alert(
                investigation_id=investigation_id,
                alert_id=alert_id,
                alert_service=alert_service,  # two-sided consistency
            )
        )
    except InvestigationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/{investigation_id}/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append an immutable note to the investigation timeline",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_CREATE))],
)
async def add_note(
    investigation_id: uuid.UUID,
    body: NoteCreateRequest,
    current_user: User = Depends(require_active_user),
    service: InvestigationService = Depends(get_investigation_service),
):
    try:
        note = await service.add_note(
            investigation_id=investigation_id,
            author_id=str(current_user.id),
            content=body.content,
        )
    except InvestigationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _note_to_response(note)


@router.get(
    "/{investigation_id}/notes",
    response_model=NoteListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve the investigation timeline (notes in chronological order)",
    dependencies=[Depends(require_permission(PermissionName.INVESTIGATIONS_READ))],
)
async def list_notes(
    investigation_id: uuid.UUID,
    service: InvestigationService = Depends(get_investigation_service),
):
    try:
        notes = await service.list_notes(investigation_id)
    except InvestigationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return NoteListResponse(
        investigation_id=str(investigation_id),
        notes=[_note_to_response(n) for n in notes],
        count=len(notes),
    )
