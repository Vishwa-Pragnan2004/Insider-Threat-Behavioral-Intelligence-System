"""
ITBIS — Investigations Module: MongoDB Repositories
"""
import uuid
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.investigations.domain.entities import (
    Investigation,
    InvestigationNote,
)
from app.modules.investigations.domain.enums import InvestigationStatus
from app.modules.investigations.domain.repositories import (
    IInvestigationNoteRepository,
    IInvestigationRepository,
)

# ─── Investigation ────────────────────────────────────────


class MongoInvestigationRepository(IInvestigationRepository):
    """
    MongoDB persistence for Investigation.

    Indexes (created on first use):
      - status
      - assigned_to
      - created_at
      - related_user_ids
      - severity
    """

    COLLECTION = "investigations"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self._indexes_built = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_built:
            return
        coll = self.db[self.COLLECTION]
        await coll.create_index("status", name="ix_inv_status")
        await coll.create_index("assigned_to", name="ix_inv_assigned")
        await coll.create_index("created_at", name="ix_inv_created_at")
        await coll.create_index("related_user_ids", name="ix_inv_related_users")
        await coll.create_index("severity", name="ix_inv_severity")
        self._indexes_built = True

    @staticmethod
    def _to_doc(i: Investigation) -> dict:
        return {
            "_id": str(i.id),
            "title": i.title,
            "description": i.description,
            "severity": i.severity,
            "status": i.status.value,
            "created_by": i.created_by,
            "assigned_to": i.assigned_to,
            "related_alert_ids": [str(a) for a in i.related_alert_ids],
            "related_user_ids": list(i.related_user_ids),
            "resolution": i.resolution,
            "created_at": i.created_at,
            "updated_at": i.updated_at,
            "closed_at": i.closed_at,
        }

    @staticmethod
    def _from_doc(doc: dict) -> Investigation:
        def _to_dt(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value

        return Investigation(
            id=uuid.UUID(doc["_id"]) if isinstance(doc.get("_id"), str) else uuid.uuid4(),
            title=doc["title"],
            description=doc.get("description", ""),
            severity=doc.get("severity", "MEDIUM"),
            created_by=doc.get("created_by", "unknown"),
            assigned_to=doc.get("assigned_to"),
            related_alert_ids=[
                uuid.UUID(a) for a in doc.get("related_alert_ids", []) or []
            ],
            related_user_ids=list(doc.get("related_user_ids", []) or []),
            resolution=doc.get("resolution"),
            status=InvestigationStatus(doc.get("status", "OPEN")),
            created_at=_to_dt(doc.get("created_at")),
            updated_at=_to_dt(doc.get("updated_at")),
            closed_at=_to_dt(doc.get("closed_at")),
        )

    async def upsert(self, investigation: Investigation) -> Investigation:
        await self._ensure_indexes()
        await self.db[self.COLLECTION].update_one(
            {"_id": str(investigation.id)},
            {"$set": self._to_doc(investigation)},
            upsert=True,
        )
        return investigation

    async def get_by_id(self, investigation_id: uuid.UUID) -> Investigation | None:
        await self._ensure_indexes()
        doc = await self.db[self.COLLECTION].find_one(
            {"_id": str(investigation_id)}
        )
        return self._from_doc(doc) if doc else None

    async def list_investigations(
        self,
        *,
        status: InvestigationStatus | None = None,
        assigned_to: str | None = None,
        severity: str | None = None,
        related_user_id: str | None = None,
        created_by: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Investigation]:
        await self._ensure_indexes()
        q: dict = {}
        if status is not None:
            q["status"] = status.value
        if assigned_to is not None:
            q["assigned_to"] = assigned_to
        if severity is not None:
            q["severity"] = severity
        if related_user_id is not None:
            q["related_user_ids"] = related_user_id
        if created_by is not None:
            q["created_by"] = created_by
        cursor = (
            self.db[self.COLLECTION]
            .find(q)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [self._from_doc(d) async for d in cursor]

    async def count_investigations(
        self,
        *,
        status: InvestigationStatus | None = None,
        assigned_to: str | None = None,
        severity: str | None = None,
        related_user_id: str | None = None,
        created_by: str | None = None,
    ) -> int:
        await self._ensure_indexes()
        q: dict = {}
        if status is not None:
            q["status"] = status.value
        if assigned_to is not None:
            q["assigned_to"] = assigned_to
        if severity is not None:
            q["severity"] = severity
        if related_user_id is not None:
            q["related_user_ids"] = related_user_id
        if created_by is not None:
            q["created_by"] = created_by
        return int(await self.db[self.COLLECTION].count_documents(q))


# ─── Investigation Note ──────────────────────────────────


class MongoInvestigationNoteRepository(IInvestigationNoteRepository):
    """
    MongoDB persistence for InvestigationNote.

    Indexes (created on first use):
      - investigation_id
      - created_at
    """

    COLLECTION = "investigation_notes"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self._indexes_built = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_built:
            return
        coll = self.db[self.COLLECTION]
        await coll.create_index("investigation_id", name="ix_note_investigation")
        await coll.create_index("created_at", name="ix_note_created_at")
        self._indexes_built = True

    @staticmethod
    def _to_doc(n: InvestigationNote) -> dict:
        return {
            "_id": str(n.id),
            "investigation_id": str(n.investigation_id),
            "author_id": n.author_id,
            "content": n.content,
            "created_at": n.created_at,
        }

    @staticmethod
    def _from_doc(doc: dict) -> InvestigationNote:
        def _to_dt(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value

        return InvestigationNote(
            id=uuid.UUID(doc["_id"]) if isinstance(doc.get("_id"), str) else uuid.uuid4(),
            investigation_id=uuid.UUID(doc["investigation_id"]),
            author_id=doc["author_id"],
            content=doc["content"],
            created_at=_to_dt(doc.get("created_at")),
        )

    async def append(self, note: InvestigationNote) -> None:
        await self._ensure_indexes()
        await self.db[self.COLLECTION].insert_one(self._to_doc(note))

    async def list_for_investigation(
        self, investigation_id: uuid.UUID
    ) -> list[InvestigationNote]:
        await self._ensure_indexes()
        cursor = (
            self.db[self.COLLECTION]
            .find({"investigation_id": str(investigation_id)})
            .sort("created_at", 1)
        )
        return [self._from_doc(d) async for d in cursor]
