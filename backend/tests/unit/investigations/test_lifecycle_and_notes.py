"""
ITBIS — Unit tests: Investigation lifecycle + notes.

Covers:
  - allowed status transitions
  - illegal status transitions
  - closed_at is set on CLOSED
  - self-loops are no-ops
  - link/unlink alert
  - add_note + list_notes (notes are immutable)
  - notes preserve author and content
  - assign investigator
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.investigations.application.investigation_service import (
    InvestigationService,
)
from app.modules.investigations.domain.entities import (
    Investigation,
    InvestigationNote,
)
from app.modules.investigations.domain.enums import InvestigationStatus, is_valid_transition
from app.modules.investigations.domain.exceptions import (
    IllegalInvestigationStatusTransitionError,
    InvestigationNotFoundError,
)
from app.modules.investigations.domain.repositories import (
    IInvestigationNoteRepository,
    IInvestigationRepository,
)

# ─── Lifecycle: allowed transitions ──────────────────────


def test_open_to_in_progress_is_allowed():
    assert is_valid_transition(InvestigationStatus.OPEN, InvestigationStatus.IN_PROGRESS)


def test_in_progress_to_resolved_is_allowed():
    assert is_valid_transition(
        InvestigationStatus.IN_PROGRESS, InvestigationStatus.RESOLVED
    )


def test_resolved_to_closed_is_allowed():
    assert is_valid_transition(InvestigationStatus.RESOLVED, InvestigationStatus.CLOSED)


def test_in_progress_to_open_is_allowed():
    assert is_valid_transition(InvestigationStatus.IN_PROGRESS, InvestigationStatus.OPEN)


def test_resolved_to_in_progress_is_allowed():
    assert is_valid_transition(InvestigationStatus.RESOLVED, InvestigationStatus.IN_PROGRESS)


# ─── Lifecycle: illegal transitions ────────────────────


def test_open_to_resolved_is_illegal():
    assert not is_valid_transition(InvestigationStatus.OPEN, InvestigationStatus.RESOLVED)


def test_open_to_closed_is_illegal():
    assert not is_valid_transition(InvestigationStatus.OPEN, InvestigationStatus.CLOSED)


def test_closed_is_terminal():
    for s in InvestigationStatus:
        if s == InvestigationStatus.CLOSED:
            continue
        assert not is_valid_transition(InvestigationStatus.CLOSED, s), (
            f"CLOSED should be terminal but allowed {s}"
        )


# ─── Entity behaviour ───────────────────────────────────


def _make_inv(**overrides) -> Investigation:
    defaults = dict(
        title="t",
        description="d",
        severity="HIGH",
        created_by="creator",
    )
    defaults.update(overrides)
    return Investigation(**defaults)


def test_change_status_walks_full_lifecycle():
    inv = _make_inv()
    assert inv.status == InvestigationStatus.OPEN
    inv.change_status(InvestigationStatus.IN_PROGRESS)
    inv.change_status(InvestigationStatus.RESOLVED)
    inv.change_status(InvestigationStatus.CLOSED)
    assert inv.status == InvestigationStatus.CLOSED
    assert inv.closed_at is not None


def test_change_status_to_illegal_raises_value_error():
    inv = _make_inv()
    with pytest.raises(ValueError):
        inv.change_status(InvestigationStatus.RESOLVED)  # OPEN -> RESOLVED illegal


def test_self_loop_change_status_is_noop():
    inv = _make_inv()
    closed_at_before = inv.closed_at
    inv.change_status(InvestigationStatus.OPEN)  # self-loop
    assert inv.status == InvestigationStatus.OPEN
    assert inv.closed_at == closed_at_before  # no change


def test_add_alert_dedupes_and_links_user():
    inv = _make_inv()
    aid = uuid.uuid4()
    inv.add_alert(aid, "alice")
    inv.add_alert(aid, "alice")  # duplicate
    assert inv.related_alert_ids == [aid]
    assert inv.related_user_ids == ["alice"]


def test_remove_alert_clears_id():
    inv = _make_inv()
    aid = uuid.uuid4()
    inv.add_alert(aid, "alice")
    inv.remove_alert(aid)
    assert aid not in inv.related_alert_ids


def test_assign_sets_user():
    inv = _make_inv()
    inv.assign("alice")
    assert inv.assigned_to == "alice"


# ─── Notes immutability ──────────────────────────────────


def test_note_is_frozen_dataclass():
    n = InvestigationNote(
        investigation_id=uuid.uuid4(), author_id="alice", content="initial"
    )
    with pytest.raises((AttributeError, Exception)):
        n.content = "modified"  # type: ignore[misc]


def test_note_preserves_author_and_content():
    n = InvestigationNote(
        investigation_id=uuid.uuid4(),
        author_id="alice",
        content="this is the note",
    )
    assert n.author_id == "alice"
    assert n.content == "this is the note"
    assert n.created_at is not None


# ─── Service: notes ─────────────────────────────────────


class FakeInvestigationRepo(IInvestigationRepository):
    def __init__(self) -> None:
        self.docs: dict[uuid.UUID, Investigation] = {}

    async def upsert(self, investigation: Investigation) -> Investigation:
        self.docs[investigation.id] = investigation
        return investigation

    async def get_by_id(self, investigation_id: uuid.UUID) -> Investigation | None:
        return self.docs.get(investigation_id)

    async def list_investigations(
        self, *, status=None, assigned_to=None, severity=None,
        related_user_id=None, created_by=None, skip=0, limit=50,
    ):
        items = list(self.docs.values())
        if status is not None:
            items = [i for i in items if i.status == status]
        if assigned_to is not None:
            items = [i for i in items if i.assigned_to == assigned_to]
        if severity is not None:
            items = [i for i in items if i.severity == severity]
        if related_user_id is not None:
            items = [i for i in items if related_user_id in i.related_user_ids]
        if created_by is not None:
            items = [i for i in items if i.created_by == created_by]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[skip:][:limit]

    async def count_investigations(self, **kwargs):
        items = await self.list_investigations(
            **{k: v for k, v in kwargs.items() if k not in ("skip", "limit")}
        )
        return len(items)


class FakeNoteRepo(IInvestigationNoteRepository):
    def __init__(self) -> None:
        self.notes: list[InvestigationNote] = []

    async def append(self, note: InvestigationNote) -> None:
        self.notes.append(note)

    async def list_for_investigation(self, investigation_id):
        return sorted(
            [n for n in self.notes if n.investigation_id == investigation_id],
            key=lambda n: n.created_at,
        )


class FakeUserDirectory:
    """Permissive user-existence stub — tests can override `exists`."""

    def __init__(self) -> None:
        self.exists_map: dict[str, bool] = {}

    async def user_exists(self, user_id: str) -> bool:
        return self.exists_map.get(user_id, True)


@pytest.fixture
def service():
    inv_repo = FakeInvestigationRepo()
    note_repo = FakeNoteRepo()
    user_dir = FakeUserDirectory()
    return (
        inv_repo,
        note_repo,
        InvestigationService(inv_repo, note_repo, user_directory=user_dir),
        user_dir,
    )


@pytest.mark.asyncio
async def test_create_persists_and_uses_creator(service):
    inv_repo, _, svc, _user_dir = service
    inv = await svc.create(
        title="phishing",
        description="check this",
        severity="HIGH",
        created_by="alice",
        related_alert_ids=[uuid.uuid4()],
        related_user_ids=["bob"],
    )
    assert inv.title == "phishing"
    assert inv.created_by == "alice"
    assert inv.status == InvestigationStatus.OPEN
    assert inv.id in inv_repo.docs


@pytest.mark.asyncio
async def test_add_note_appears_in_list_in_chronological_order(service):
    _, _, svc, _ = service
    inv = await svc.create(
        title="x", description="", severity="LOW",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    n1 = await svc.add_note(inv.id, "alice", "first")
    n2 = await svc.add_note(inv.id, "bob", "second")
    notes = await svc.list_notes(inv.id)
    assert notes == [n1, n2]
    assert notes[0].author_id == "alice"
    assert notes[1].content == "second"


@pytest.mark.asyncio
async def test_add_note_to_missing_investigation_raises(service):
    _, _, svc, _ = service
    with pytest.raises(InvestigationNotFoundError):
        await svc.add_note(uuid.uuid4(), "alice", "x")


@pytest.mark.asyncio
async def test_list_notes_for_missing_investigation_raises(service):
    _, _, svc, _ = service
    with pytest.raises(InvestigationNotFoundError):
        await svc.list_notes(uuid.uuid4())


@pytest.mark.asyncio
async def test_status_change_walks_lifecycle(service):
    inv_repo, _, svc, _user_dir = service
    inv = await svc.create(
        title="t", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    await svc.change_status(inv.id, InvestigationStatus.IN_PROGRESS)
    await svc.change_status(inv.id, InvestigationStatus.RESOLVED)
    await svc.change_status(inv.id, InvestigationStatus.CLOSED)
    final = await svc.get(inv.id)
    assert final.status == InvestigationStatus.CLOSED
    assert final.closed_at is not None


@pytest.mark.asyncio
async def test_status_change_illegal_raises(service):
    _, _, svc, _ = service
    inv = await svc.create(
        title="t", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    # OPEN -> RESOLVED is illegal
    with pytest.raises(IllegalInvestigationStatusTransitionError):
        await svc.change_status(inv.id, InvestigationStatus.RESOLVED)


@pytest.mark.asyncio
async def test_add_alert_link_persists(service):
    _, _, svc, _ = service
    inv = await svc.create(
        title="t", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    aid = uuid.uuid4()
    saved = await svc.add_alert(inv.id, aid, "bob")
    assert aid in saved.related_alert_ids
    assert "bob" in saved.related_user_ids


@pytest.mark.asyncio
async def test_assign_persists(service):
    _, _, svc, _ = service
    inv = await svc.create(
        title="t", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    saved = await svc.assign(inv.id, "bob")
    assert saved.assigned_to == "bob"


# ─── FIX 3: assignment validates that the target user exists ────────


@pytest.mark.asyncio
async def test_assign_investigation_to_existing_user_succeeds(service):
    inv_repo, _, svc, user_dir = service
    inv = await svc.create(
        title="valid title",
        description="d",
        severity="HIGH",
        created_by="alice",
        related_alert_ids=[],
        related_user_ids=[],
    )
    user_dir.exists_map["real-user"] = True
    saved = await svc.assign(inv.id, "real-user")
    assert saved.assigned_to == "real-user"


@pytest.mark.asyncio
async def test_assign_investigation_to_nonexistent_user_raises(service):
    from app.modules.investigations.domain.exceptions import AssigneeNotFoundError

    inv_repo, _, svc, user_dir = service
    inv = await svc.create(
        title="valid title",
        description="d",
        severity="HIGH",
        created_by="alice",
        related_alert_ids=[],
        related_user_ids=[],
    )
    user_dir.exists_map["ghost-user"] = False
    with pytest.raises(AssigneeNotFoundError) as exc_info:
        await svc.assign(inv.id, "ghost-user")
    assert "ghost-user" in str(exc_info.value)
    # The investigation was not updated in the repo.
    assert inv_repo.docs[inv.id].assigned_to is None


@pytest.mark.asyncio
async def test_assign_investigation_to_existing_user_does_not_raise(service):
    inv_repo, _, svc, user_dir = service
    inv = await svc.create(
        title="valid title",
        description="d",
        severity="HIGH",
        created_by="alice",
        related_alert_ids=[],
        related_user_ids=[],
    )
    user_dir.exists_map["real-user"] = True
    saved = await svc.assign(inv.id, "real-user")
    assert saved.assigned_to == "real-user"


# ─── FIX 4: link/unlink two-sided consistency + idempotency ─────


class FakeAlertService:
    """
    In-memory stand-in for AlertService used to assert the alert-side
    effects of InvestigationService.add_alert / remove_alert.

    Records every call and exposes a tiny dict of alerts so the test
    can verify the alert's `investigation_id` is set/cleared in sync
    with the investigation's `related_alert_ids`.
    """

    def __init__(self) -> None:
        self.alerts: dict[uuid.UUID, dict] = {}
        self.link_calls: list = []  # list of (alert_id, investigation_id)
        self.unlink_calls: list = []  # list of (alert_id,)
        self.raise_on_link: Exception | None = None
        self.raise_on_unlink: Exception | None = None

    async def link_investigation(
        self, alert_id: uuid.UUID, investigation_id: uuid.UUID
    ) -> None:
        if self.raise_on_link is not None:
            raise self.raise_on_link
        self.link_calls.append((alert_id, investigation_id))
        a = self.alerts.setdefault(alert_id, {"investigation_id": None})
        a["investigation_id"] = investigation_id

    async def unlink_investigation(self, alert_id: uuid.UUID) -> None:
        if self.raise_on_unlink is not None:
            raise self.raise_on_unlink
        self.unlink_calls.append((alert_id,))
        if alert_id in self.alerts:
            self.alerts[alert_id]["investigation_id"] = None

    async def get(self, alert_id: uuid.UUID):
        return self.alerts.get(alert_id)


@pytest.mark.asyncio
async def test_add_alert_links_both_sides(service):
    """FIX 4: linking an alert must update the investigation side AND
    the alert side (two-sided invariant)."""
    inv_repo, _, svc, _ = service
    alert_svc = FakeAlertService()
    inv = await svc.create(
        title="valid title", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    aid = uuid.uuid4()
    alert_svc.alerts[aid] = {"investigation_id": None}

    await svc.add_alert(inv.id, aid, user_id=None, alert_service=alert_svc)

    # Investigation side updated.
    assert aid in inv_repo.docs[inv.id].related_alert_ids
    # Alert side updated.
    assert alert_svc.alerts[aid]["investigation_id"] == inv.id
    # Exactly one call was made.
    assert alert_svc.link_calls == [(aid, inv.id)]


@pytest.mark.asyncio
async def test_add_alert_is_idempotent(service):
    """FIX 4: linking the same alert twice must NOT create a duplicate
    reference in the investigation, and must NOT re-call the alert service."""
    inv_repo, _, svc, _ = service
    alert_svc = FakeAlertService()
    inv = await svc.create(
        title="valid title", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    aid = uuid.uuid4()
    alert_svc.alerts[aid] = {"investigation_id": None}

    await svc.add_alert(inv.id, aid, user_id=None, alert_service=alert_svc)
    await svc.add_alert(inv.id, aid, user_id=None, alert_service=alert_svc)
    await svc.add_alert(inv.id, aid, user_id=None, alert_service=alert_svc)

    # Still exactly one entry in the investigation.
    assert inv_repo.docs[inv.id].related_alert_ids == [aid]
    # The alert service was called only once (the second/third
    # calls were idempotent short-circuited at the service level).
    assert len(alert_svc.link_calls) == 1


@pytest.mark.asyncio
async def test_remove_alert_unlinks_both_sides(service):
    """FIX 4: unlinking an alert must clear it from the investigation
    AND clear the alert's investigation_id."""
    inv_repo, _, svc, _ = service
    alert_svc = FakeAlertService()
    inv = await svc.create(
        title="valid title", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    aid = uuid.uuid4()
    # Pre-link so we can unlink.
    alert_svc.alerts[aid] = {"investigation_id": None}
    await svc.add_alert(inv.id, aid, user_id=None, alert_service=alert_svc)
    # Sanity: linked on both sides.
    assert aid in inv_repo.docs[inv.id].related_alert_ids
    assert alert_svc.alerts[aid]["investigation_id"] == inv.id

    await svc.remove_alert(inv.id, aid, alert_service=alert_svc)

    # Both sides cleared.
    assert aid not in inv_repo.docs[inv.id].related_alert_ids
    assert alert_svc.alerts[aid]["investigation_id"] is None
    assert alert_svc.unlink_calls == [(aid,)]


@pytest.mark.asyncio
async def test_remove_alert_is_idempotent(service):
    """FIX 4: unlinking an alert that is not linked is a no-op (does
    not raise, does not call the alert service)."""
    inv_repo, _, svc, _ = service
    alert_svc = FakeAlertService()
    inv = await svc.create(
        title="valid title", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    aid = uuid.uuid4()
    # aid was never linked.
    await svc.remove_alert(inv.id, aid, alert_service=alert_svc)
    # The alert service was NOT called.
    assert alert_svc.unlink_calls == []
    # The investigation was not mutated.
    assert inv_repo.docs[inv.id].related_alert_ids == []


@pytest.mark.asyncio
async def test_add_alert_alert_service_failure_raises_and_logs(service):
    """FIX 4: if the alert-side update fails, the service re-raises
    (the investigation side was already persisted; this is the
    documented behaviour — see the docstring of add_alert)."""
    inv_repo, _, svc, _ = service
    alert_svc = FakeAlertService()
    alert_svc.raise_on_link = RuntimeError("alert-side blew up")
    inv = await svc.create(
        title="valid title", description="", severity="HIGH",
        created_by="alice", related_alert_ids=[], related_user_ids=[],
    )
    aid = uuid.uuid4()

    with pytest.raises(RuntimeError):
        await svc.add_alert(inv.id, aid, user_id=None, alert_service=alert_svc)
    # The investigation side was persisted before the alert side was
    # attempted.
    assert aid in inv_repo.docs[inv.id].related_alert_ids
