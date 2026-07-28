from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from market_trader.broker.schwab.tokens import (
    SchwabTokenBundle,
    SchwabTokenCipher,
    SchwabTokenEncryptionError,
    SchwabTokenRepository,
)
from market_trader.db.base import Base
from market_trader.db.engine import create_engine_from_url

NOW = datetime(2026, 7, 27, 14, 30, tzinfo=UTC)


@pytest.fixture()
def session(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'tokens.db'}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db_session:
            yield db_session
    finally:
        engine.dispose()


def test_cipher_encrypts_tokens_and_rejects_wrong_key() -> None:
    bundle = _bundle("access-token-a", "refresh-token-a")
    encrypted = SchwabTokenCipher("local-encryption-key-a").encrypt(bundle)

    assert "access-token-a" not in repr(encrypted)
    assert "refresh-token-a" not in repr(encrypted)
    assert SchwabTokenCipher("local-encryption-key-a").decrypt(encrypted) == bundle
    with pytest.raises(SchwabTokenEncryptionError, match="authentication failed"):
        SchwabTokenCipher("wrong-local-encryption-key").decrypt(encrypted)


def test_cipher_rejects_missing_key() -> None:
    with pytest.raises(SchwabTokenEncryptionError, match="encryption key is required"):
        SchwabTokenCipher("")


def test_repository_stores_encrypted_tokens_and_exposes_metadata_only(
    session: Session,
) -> None:
    repository = SchwabTokenRepository(SchwabTokenCipher("local-encryption-key-a"))
    bundle = _bundle("access-token-a", "refresh-token-a")

    repository.store_initial(
        session,
        token_id="token-market-data",
        product="market_data",
        bundle=bundle,
        now=NOW,
        correlation_id="corr-token",
    )

    metadata = repository.metadata(session, token_id="token-market-data", now=NOW)
    assert metadata.status == "active"
    assert metadata.product == "market_data"
    assert metadata.access_token_expires_at == NOW + timedelta(minutes=30)
    assert metadata.is_expired is False
    assert "access-token-a" not in repr(metadata)
    assert "refresh-token-a" not in repr(metadata)
    assert repository.read(session, token_id="token-market-data") == bundle


def test_repository_rotates_refresh_tokens(session: Session) -> None:
    repository = SchwabTokenRepository(SchwabTokenCipher("local-encryption-key-a"))
    repository.store_initial(
        session,
        token_id="token-market-data",
        product="market_data",
        bundle=_bundle("access-token-a", "refresh-token-a"),
        now=NOW,
        correlation_id="corr-token",
    )

    repository.rotate(
        session,
        token_id="token-market-data",
        bundle=_bundle("access-token-b", "refresh-token-b"),
        now=NOW + timedelta(minutes=5),
    )

    metadata = repository.metadata(
        session,
        token_id="token-market-data",
        now=NOW + timedelta(minutes=5),
    )
    assert metadata.refreshed_at == NOW + timedelta(minutes=5)
    assert repository.read(session, token_id="token-market-data").access_token == (
        "access-token-b"
    )


def test_repository_revokes_tokens_and_blocks_secret_reads(session: Session) -> None:
    repository = SchwabTokenRepository(SchwabTokenCipher("local-encryption-key-a"))
    repository.store_initial(
        session,
        token_id="token-market-data",
        product="market_data",
        bundle=_bundle("access-token-a", "refresh-token-a"),
        now=NOW,
        correlation_id="corr-token",
    )

    repository.revoke(
        session,
        token_id="token-market-data",
        now=NOW + timedelta(minutes=10),
        reason_code="operator_revoked",
    )

    metadata = repository.metadata(
        session,
        token_id="token-market-data",
        now=NOW + timedelta(minutes=10),
    )
    assert metadata.status == "revoked"
    assert metadata.revoked_at == NOW + timedelta(minutes=10)
    assert metadata.last_error_code == "operator_revoked"
    with pytest.raises(LookupError, match="not active"):
        repository.read(session, token_id="token-market-data")


def test_repository_reports_expired_tokens(session: Session) -> None:
    repository = SchwabTokenRepository(SchwabTokenCipher("local-encryption-key-a"))
    repository.store_initial(
        session,
        token_id="token-market-data",
        product="market_data",
        bundle=_bundle("access-token-a", "refresh-token-a"),
        now=NOW,
        correlation_id="corr-token",
    )

    metadata = repository.metadata(
        session,
        token_id="token-market-data",
        now=NOW + timedelta(minutes=31),
    )

    assert metadata.is_expired is True


def _bundle(access_token: str, refresh_token: str) -> SchwabTokenBundle:
    return SchwabTokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        scope="read:market_data",
        access_token_expires_at=NOW + timedelta(minutes=30),
        refresh_token_expires_at=NOW + timedelta(days=7),
    )
