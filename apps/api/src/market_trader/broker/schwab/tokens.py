from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import SchwabTokenORM
from market_trader.domain.time import ensure_utc

_ALGORITHM = "pbkdf2-hmac-sha256+hmac-keystream-v1"
_PBKDF2_ITERATIONS = 200_000


class SchwabTokenEncryptionError(ValueError):
    pass


@dataclass(frozen=True)
class SchwabTokenBundle:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    token_type: str
    scope: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "access_token_expires_at",
            _db_utc(self.access_token_expires_at),
        )
        if self.refresh_token_expires_at is not None:
            object.__setattr__(
                self,
                "refresh_token_expires_at",
                _db_utc(self.refresh_token_expires_at),
            )


@dataclass(frozen=True)
class EncryptedTokenEnvelope:
    algorithm: str
    key_id: str
    salt: str = field(repr=False)
    nonce: str = field(repr=False)
    ciphertext: str = field(repr=False)
    tag: str = field(repr=False)

    def to_payload(self) -> dict[str, str]:
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "salt": self.salt,
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
            "tag": self.tag,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> EncryptedTokenEnvelope:
        return cls(
            algorithm=str(payload["algorithm"]),
            key_id=str(payload["key_id"]),
            salt=str(payload["salt"]),
            nonce=str(payload["nonce"]),
            ciphertext=str(payload["ciphertext"]),
            tag=str(payload["tag"]),
        )


@dataclass(frozen=True)
class SchwabTokenMetadata:
    token_id: str
    product: str
    status: str
    token_type: str
    scope: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime | None
    encryption_key_id: str
    issued_at: datetime
    refreshed_at: datetime | None
    revoked_at: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None
    is_expired: bool


class SchwabTokenCipher:
    def __init__(self, encryption_key: str) -> None:
        if not encryption_key:
            raise SchwabTokenEncryptionError("encryption key is required")
        self._encryption_key = encryption_key.encode("utf-8")
        self.key_id = hashlib.sha256(self._encryption_key).hexdigest()[:16]

    def encrypt(self, bundle: SchwabTokenBundle) -> EncryptedTokenEnvelope:
        payload = {
            "access_token": bundle.access_token,
            "refresh_token": bundle.refresh_token,
            "token_type": bundle.token_type,
            "scope": bundle.scope,
            "access_token_expires_at": bundle.access_token_expires_at.isoformat(),
            "refresh_token_expires_at": (
                bundle.refresh_token_expires_at.isoformat()
                if bundle.refresh_token_expires_at is not None
                else None
            ),
        }
        return self.encrypt_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    def decrypt(self, envelope: EncryptedTokenEnvelope) -> SchwabTokenBundle:
        payload = json.loads(self.decrypt_text(envelope))
        refresh_expires = payload["refresh_token_expires_at"]
        return SchwabTokenBundle(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            token_type=str(payload["token_type"]),
            scope=str(payload["scope"]),
            access_token_expires_at=datetime.fromisoformat(
                str(payload["access_token_expires_at"])
            ),
            refresh_token_expires_at=(
                datetime.fromisoformat(str(refresh_expires))
                if refresh_expires is not None
                else None
            ),
        )

    def encrypt_text(self, plaintext: str) -> EncryptedTokenEnvelope:
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(16)
        encryption_key, mac_key = self._derive_keys(salt)
        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext = _xor_bytes(
            plaintext_bytes,
            _keystream(encryption_key, nonce, len(plaintext_bytes)),
        )
        tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        return EncryptedTokenEnvelope(
            algorithm=_ALGORITHM,
            key_id=self.key_id,
            salt=_b64encode(salt),
            nonce=_b64encode(nonce),
            ciphertext=_b64encode(ciphertext),
            tag=_b64encode(tag),
        )

    def decrypt_text(self, envelope: EncryptedTokenEnvelope) -> str:
        if envelope.algorithm != _ALGORITHM:
            raise SchwabTokenEncryptionError("unsupported token encryption algorithm")
        if envelope.key_id != self.key_id:
            raise SchwabTokenEncryptionError("token authentication failed")
        salt = _b64decode(envelope.salt)
        nonce = _b64decode(envelope.nonce)
        ciphertext = _b64decode(envelope.ciphertext)
        expected_tag = _b64decode(envelope.tag)
        encryption_key, mac_key = self._derive_keys(salt)
        actual_tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_tag, expected_tag):
            raise SchwabTokenEncryptionError("token authentication failed")
        plaintext = _xor_bytes(ciphertext, _keystream(encryption_key, nonce, len(ciphertext)))
        return plaintext.decode("utf-8")

    def _derive_keys(self, salt: bytes) -> tuple[bytes, bytes]:
        key_material = hashlib.pbkdf2_hmac(
            "sha256",
            self._encryption_key,
            salt,
            _PBKDF2_ITERATIONS,
            dklen=64,
        )
        return key_material[:32], key_material[32:]


class SchwabTokenRepository:
    def __init__(self, cipher: SchwabTokenCipher) -> None:
        self._cipher = cipher

    def store_initial(
        self,
        session: Session,
        *,
        token_id: str,
        product: str,
        bundle: SchwabTokenBundle,
        now: datetime,
        correlation_id: str,
    ) -> None:
        created_at = ensure_utc(now)
        session.add(
            SchwabTokenORM(
                id=token_id,
                product=product,
                status="active",
                encrypted_access_token=self._cipher.encrypt_text(bundle.access_token).to_payload(),
                encrypted_refresh_token=self._cipher.encrypt_text(bundle.refresh_token).to_payload(),
                token_type=bundle.token_type,
                scope=bundle.scope,
                access_token_expires_at=bundle.access_token_expires_at,
                refresh_token_expires_at=bundle.refresh_token_expires_at,
                encryption_key_id=self._cipher.key_id,
                issued_at=created_at,
                refreshed_at=None,
                revoked_at=None,
                last_error_code=None,
                last_error_at=None,
                correlation_id=correlation_id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.flush()

    def read(self, session: Session, *, token_id: str) -> SchwabTokenBundle:
        token = self._get(session, token_id)
        if token.status != "active":
            raise LookupError("Schwab token is not active")
        return SchwabTokenBundle(
            access_token=self._cipher.decrypt_text(
                EncryptedTokenEnvelope.from_payload(token.encrypted_access_token)
            ),
            refresh_token=self._cipher.decrypt_text(
                EncryptedTokenEnvelope.from_payload(token.encrypted_refresh_token)
            ),
            token_type=token.token_type,
            scope=token.scope,
            access_token_expires_at=token.access_token_expires_at,
            refresh_token_expires_at=token.refresh_token_expires_at,
        )

    def metadata(
        self,
        session: Session,
        *,
        token_id: str,
        now: datetime,
    ) -> SchwabTokenMetadata:
        token = self._get(session, token_id)
        checked_at = ensure_utc(now)
        expires_at = _db_utc(token.access_token_expires_at)
        return SchwabTokenMetadata(
            token_id=token.id,
            product=token.product,
            status=token.status,
            token_type=token.token_type,
            scope=token.scope,
            access_token_expires_at=expires_at,
            refresh_token_expires_at=(
                _db_utc(token.refresh_token_expires_at)
                if token.refresh_token_expires_at is not None
                else None
            ),
            encryption_key_id=token.encryption_key_id,
            issued_at=_db_utc(token.issued_at),
            refreshed_at=(
                _db_utc(token.refreshed_at) if token.refreshed_at is not None else None
            ),
            revoked_at=_db_utc(token.revoked_at) if token.revoked_at is not None else None,
            last_error_code=token.last_error_code,
            last_error_at=(
                _db_utc(token.last_error_at) if token.last_error_at is not None else None
            ),
            is_expired=checked_at >= expires_at,
        )

    def rotate(
        self,
        session: Session,
        *,
        token_id: str,
        bundle: SchwabTokenBundle,
        now: datetime,
    ) -> None:
        token = self._get(session, token_id)
        updated_at = ensure_utc(now)
        token.status = "active"
        token.encrypted_access_token = self._cipher.encrypt_text(bundle.access_token).to_payload()
        token.encrypted_refresh_token = self._cipher.encrypt_text(bundle.refresh_token).to_payload()
        token.token_type = bundle.token_type
        token.scope = bundle.scope
        token.access_token_expires_at = bundle.access_token_expires_at
        token.refresh_token_expires_at = bundle.refresh_token_expires_at
        token.encryption_key_id = self._cipher.key_id
        token.refreshed_at = updated_at
        token.revoked_at = None
        token.last_error_code = None
        token.last_error_at = None
        token.updated_at = updated_at
        session.flush()

    def revoke(
        self,
        session: Session,
        *,
        token_id: str,
        now: datetime,
        reason_code: str,
    ) -> None:
        token = self._get(session, token_id)
        updated_at = ensure_utc(now)
        token.status = "revoked"
        token.revoked_at = updated_at
        token.last_error_code = reason_code
        token.last_error_at = updated_at
        token.updated_at = updated_at
        session.flush()

    def _get(self, session: Session, token_id: str) -> SchwabTokenORM:
        token = session.scalar(select(SchwabTokenORM).where(SchwabTokenORM.id == token_id))
        if token is None:
            raise LookupError(f"Schwab token {token_id!r} was not found")
        return token


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(
            hmac.new(
                key,
                nonce + counter.to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()
        )
        counter += 1
    return b"".join(blocks)[:length]


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(
        left_byte ^ right_byte for left_byte, right_byte in zip(left, right, strict=True)
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
