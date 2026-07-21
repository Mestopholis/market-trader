from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 210_000


def hash_password(password: str, *, salt: str | None = None) -> str:
    active_salt = salt or secrets.token_urlsafe(24)
    digest = _pbkdf2(password, active_salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${active_salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != _ALGORITHM or iterations <= 0:
        return False
    actual = _pbkdf2(password, salt, iterations)
    return hmac.compare_digest(actual, expected)


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
