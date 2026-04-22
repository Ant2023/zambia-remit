import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


def derive_fernet_key(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def validate_fernet_key(key: str) -> None:
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ValidationError("FIELD_ENCRYPTION_KEY must be a valid Fernet key.") from exc


@lru_cache
def get_fernet() -> Fernet:
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must be configured.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_bytes(value: bytes) -> bytes:
    return get_fernet().encrypt(value)


def decrypt_bytes(value: bytes) -> bytes:
    try:
        return get_fernet().decrypt(value)
    except InvalidToken as exc:
        raise ValidationError("Encrypted data could not be decrypted.") from exc


def encrypt_text(value: str) -> str:
    return encrypt_bytes(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str) -> str:
    if not value:
        return ""
    return decrypt_bytes(value.encode("ascii")).decode("utf-8")
