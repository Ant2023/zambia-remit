import os
import base64
import hashlib
import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def env_map(name: str, default: dict[str, str] | None = None) -> dict[str, str]:
    value = os.getenv(name)
    if value is None:
        return default or {}

    items = {}
    for item in value.split(","):
        if ":" not in item:
            continue
        key, secret = item.split(":", 1)
        key = key.strip()
        secret = secret.strip()
        if key and secret:
            items[key] = secret
    return items


def env_json(name: str, default: dict | None = None) -> dict:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default or {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            f"{name} must be valid JSON.",
        ) from exc

    if not isinstance(parsed, dict):
        raise ImproperlyConfigured(f"{name} must be a JSON object.")

    return parsed


def derive_fernet_key(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


SECRET_KEY = env("DJANGO_SECRET_KEY", "unsafe-development-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])


INSTALLED_APPS = [
    "common.apps.CommonConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "apps.accounts",
    "apps.countries",
    "apps.recipients",
    "apps.quotes",
    "apps.transfers",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "common.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [ROOT_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "zambia_remit"),
        "USER": env("POSTGRES_USER", "postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", "postgres"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "common.authentication.ExpiringTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("DRF_ANON_THROTTLE_RATE", "200/minute"),
        "user": env("DRF_USER_THROTTLE_RATE", "1200/hour"),
        "auth": env("DRF_AUTH_THROTTLE_RATE", "20/minute"),
        "password_reset": env("DRF_PASSWORD_RESET_THROTTLE_RATE", "5/minute"),
        "document_upload": env("DRF_DOCUMENT_UPLOAD_THROTTLE_RATE", "20/hour"),
        "webhook": env("DRF_WEBHOOK_THROTTLE_RATE", "600/minute"),
    },
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = ROOT_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = ROOT_DIR / "media"

AUTH_TOKEN_TTL_HOURS = env_int("AUTH_TOKEN_TTL_HOURS", 168)

_FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
FIELD_ENCRYPTION_KEY_IS_DERIVED = not bool(_FIELD_ENCRYPTION_KEY)
FIELD_ENCRYPTION_KEY = _FIELD_ENCRYPTION_KEY or derive_fernet_key(SECRET_KEY)

SECURE_DOCUMENT_MAX_UPLOAD_SIZE = env_int(
    "SECURE_DOCUMENT_MAX_UPLOAD_SIZE",
    10 * 1024 * 1024,
)
SECURE_DOCUMENT_ALLOWED_CONTENT_TYPES = env_list(
    "SECURE_DOCUMENT_ALLOWED_CONTENT_TYPES",
    ["application/pdf", "image/jpeg", "image/png"],
)
SECURE_DOCUMENT_STORAGE_ROOT = Path(
    env("SECURE_DOCUMENT_STORAGE_ROOT", str(MEDIA_ROOT / "private_documents")),
)
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 12 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 12 * 1024 * 1024)
FILE_UPLOAD_PERMISSIONS = 0o600

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "support@mbongopay.local")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
CARD_PAYMENT_PROCESSOR = env("CARD_PAYMENT_PROCESSOR", "mock_card_processor")
BANK_TRANSFER_PAYMENT_PROCESSOR = env(
    "BANK_TRANSFER_PAYMENT_PROCESSOR",
    "manual_bank_transfer",
)
PAYMENT_PROVIDER_CONFIGS = env_json("PAYMENT_PROVIDER_CONFIGS")
PAYMENT_WEBHOOK_SECRETS = env_map("PAYMENT_WEBHOOK_SECRETS")
PAYOUT_WEBHOOK_SECRETS = env_map("PAYOUT_WEBHOOK_SECRETS")

BACKUP_REQUIRED = env_bool("BACKUP_REQUIRED", False)
BACKUP_STORAGE_URL = env("BACKUP_STORAGE_URL", "")
BACKUP_ENCRYPTION_KEY = env("BACKUP_ENCRYPTION_KEY", "")
BACKUP_RETENTION_DAYS = env_int("BACKUP_RETENTION_DAYS", 30)
BACKUP_LOCAL_DIR = Path(env("BACKUP_LOCAL_DIR", str(ROOT_DIR / "backups")))

LOG_LEVEL = env("DJANGO_LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": (
                "%(asctime)s %(levelname)s %(name)s "
                "request_id=%(request_id)s user_id=%(user_id)s "
                "%(message)s"
            ),
        },
        "simple": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "filters": {
        "request_context": {
            "()": "common.logging.RequestContextFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["request_context"],
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "mbongopay.api": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "mbongopay.security": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
