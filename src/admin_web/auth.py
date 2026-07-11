from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str, *, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt_value}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_value, digest_hex = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_value.encode("utf-8"),
        120_000,
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def password_is_hashed(value: str) -> bool:
    return value.startswith("pbkdf2_sha256$")


def ensure_password_hash(password_or_hash: str) -> str:
    if password_is_hashed(password_or_hash):
        return password_or_hash
    return hash_password(password_or_hash)
