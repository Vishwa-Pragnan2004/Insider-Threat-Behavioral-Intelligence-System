"""
ITBIS — Identity Module: Agent Device Domain

An `AgentDevice` is an enrolled endpoint that is allowed to submit activity
events.  Each device holds its own credential, so a laptop can be revoked
individually without affecting any other device or any human user.

Credential format:

    itbis_ag_<reference>_<secret>

`reference` is stored in plaintext and is what we look the row up by;
`secret` is never stored — only a SHA-256 digest of it is.  Because the
secret is 256 bits of CSPRNG output there is nothing to brute-force, so a
fast digest is the right choice here (unlike user passwords, which are
low-entropy and use bcrypt).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

KEY_PREFIX = "itbis_ag"
REFERENCE_BYTES = 6      # -> 12 hex chars
SECRET_BYTES = 32        # -> 256 bits of entropy


class AgentDevice:
    """An enrolled endpoint agent and the state of its credential."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        device_id: str,
        device_name: str,
        key_reference: str,
        key_hash: str,
        is_active: bool = True,
        created_at: datetime | None = None,
        created_by: uuid.UUID | None = None,
        last_seen_at: datetime | None = None,
        revoked_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.device_id = device_id
        self.device_name = device_name
        self.key_reference = key_reference
        self.key_hash = key_hash
        self.is_active = is_active
        self.created_at = created_at or datetime.now(UTC)
        self.created_by = created_by
        self.last_seen_at = last_seen_at
        self.revoked_at = revoked_at

    # ─── Behaviour ──────────────────────────────────────────

    def revoke(self) -> None:
        """Permanently disable this device's credential."""
        self.is_active = False
        self.revoked_at = datetime.now(UTC)

    def touch(self, when: datetime | None = None) -> None:
        """Record that the device just authenticated successfully."""
        self.last_seen_at = when or datetime.now(UTC)

    def verify(self, secret: str) -> bool:
        """Constant-time check of a presented secret against the stored hash."""
        return secrets.compare_digest(self.key_hash, hash_secret(secret))

    def __repr__(self) -> str:  # pragma: no cover - trivial
        state = "active" if self.is_active else "revoked"
        return f"<AgentDevice {self.device_id} ({state})>"


# ─── Key generation / parsing ────────────────────────────────


def hash_secret(secret: str) -> str:
    """SHA-256 hex digest of a credential secret."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """
    Mint a new device credential.

    Returns `(full_key, reference, key_hash)`.  The full key is shown to the
    operator exactly once at enrollment; only the reference and hash are
    persisted.
    """
    reference = secrets.token_hex(REFERENCE_BYTES)
    secret = secrets.token_urlsafe(SECRET_BYTES)
    full_key = f"{KEY_PREFIX}_{reference}_{secret}"
    return full_key, reference, hash_secret(secret)


def parse_key(raw: str) -> tuple[str, str] | None:
    """
    Split a presented credential into `(reference, secret)`.

    Returns None when the value is not a well-formed agent key — callers
    treat that the same as an unknown key, so a malformed credential cannot
    be distinguished from a wrong one.
    """
    if not raw:
        return None
    parts = raw.strip().split("_")
    # itbis, ag, <reference>, <secret...>  — the secret may itself contain
    # underscores because it is urlsafe-base64, so rejoin the tail.
    if len(parts) < 4:
        return None
    if f"{parts[0]}_{parts[1]}" != KEY_PREFIX:
        return None
    reference = parts[2]
    secret = "_".join(parts[3:])
    if not reference or not secret:
        return None
    return reference, secret
