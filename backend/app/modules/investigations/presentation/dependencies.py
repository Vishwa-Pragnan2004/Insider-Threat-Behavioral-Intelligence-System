"""
ITBIS — Investigations Module: FastAPI Dependencies
"""
# ruff: noqa: B008
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.modules.alerts.domain.repositories import IAlertLinker
from app.modules.alerts.presentation.dependencies import get_alert_service
from app.modules.investigations.application.investigation_service import (
    InvestigationService,
)
from app.modules.investigations.domain.repositories import (
    IInvestigationNoteRepository,
    IInvestigationRepository,
    IUserDirectory,
)
from app.modules.investigations.infrastructure.mongo_investigation_repository import (
    MongoInvestigationNoteRepository,
    MongoInvestigationRepository,
)
from app.modules.investigations.infrastructure.sql_user_directory import (
    SqlUserDirectory,
)


def get_investigation_repo(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> IInvestigationRepository:
    return MongoInvestigationRepository(db)


def get_investigation_note_repo(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> IInvestigationNoteRepository:
    return MongoInvestigationNoteRepository(db)


def get_user_directory(
    session: AsyncSession = Depends(get_db),
) -> IUserDirectory:
    """SQL-backed implementation of IUserDirectory (for assignment validation)."""
    return SqlUserDirectory(session)


def get_alert_linker(
    alert_service=Depends(get_alert_service),
) -> IAlertLinker:
    """
    Expose the alerts module's link/unlink capability through the
    ``IAlertLinker`` port.  The concrete ``AlertService`` already
    implements this contract, so we return the same instance the
    alerts module constructed.  The investigations module depends
    on the abstract port — never on the concrete service class.
    """
    # ``alert_service`` is typed implicitly as the alerts service.
    # It implements IAlertLinker, so the return is type-compatible.
    return alert_service


def get_investigation_service(
    investigation_repo: IInvestigationRepository = Depends(get_investigation_repo),
    note_repo: IInvestigationNoteRepository = Depends(get_investigation_note_repo),
    user_directory: IUserDirectory = Depends(get_user_directory),
) -> InvestigationService:
    return InvestigationService(
        investigation_repo=investigation_repo,
        note_repo=note_repo,
        user_directory=user_directory,
    )
