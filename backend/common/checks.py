from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet

from .security import validate_fernet_key


@register(Tags.security, deploy=True)
def production_hardening_checks(app_configs, **kwargs):
    errors = []

    encryption_key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    try:
        validate_fernet_key(encryption_key)
    except ValidationError:
        errors.append(
            Error(
                "FIELD_ENCRYPTION_KEY must be a valid Fernet key.",
                id="mbongopay.E001",
            ),
        )

    if not settings.DEBUG and getattr(settings, "FIELD_ENCRYPTION_KEY_IS_DERIVED", False):
        errors.append(
            Error(
                "FIELD_ENCRYPTION_KEY must be set explicitly in production.",
                id="mbongopay.E002",
            ),
        )

    if not settings.DEBUG:
        if getattr(settings, "SECRET_KEY", "").startswith("unsafe-"):
            errors.append(
                Error(
                    "DJANGO_SECRET_KEY must be changed for production.",
                    id="mbongopay.E003",
                ),
            )

        if "*" in getattr(settings, "ALLOWED_HOSTS", []):
            errors.append(
                Error(
                    "DJANGO_ALLOWED_HOSTS cannot include '*' in production.",
                    id="mbongopay.E004",
                ),
            )

        if getattr(settings, "DEFAULT_FROM_EMAIL", "").endswith(".local"):
            errors.append(
                Warning(
                    "DEFAULT_FROM_EMAIL should be a real monitored production mailbox.",
                    id="mbongopay.W001",
                ),
            )

        if getattr(settings, "BACKUP_REQUIRED", True):
            if not getattr(settings, "BACKUP_STORAGE_URL", ""):
                errors.append(
                    Error(
                        "BACKUP_STORAGE_URL must be configured when backups are required.",
                        id="mbongopay.E005",
                    ),
                )
            if not getattr(settings, "BACKUP_ENCRYPTION_KEY", ""):
                errors.append(
                    Error(
                        "BACKUP_ENCRYPTION_KEY must be configured when backups are required.",
                        id="mbongopay.E006",
                    ),
                )
            else:
                try:
                    Fernet(settings.BACKUP_ENCRYPTION_KEY.encode("ascii"))
                except (TypeError, ValueError):
                    errors.append(
                        Error(
                            "BACKUP_ENCRYPTION_KEY must be a valid Fernet key.",
                            id="mbongopay.E007",
                        ),
                    )

        if not getattr(settings, "PAYMENT_WEBHOOK_SECRETS", {}):
            errors.append(
                Warning(
                    "PAYMENT_WEBHOOK_SECRETS is empty; payment webhooks will rely on network controls only.",
                    id="mbongopay.W002",
                ),
            )

        if not getattr(settings, "PAYOUT_WEBHOOK_SECRETS", {}):
            errors.append(
                Warning(
                    "PAYOUT_WEBHOOK_SECRETS is empty; payout webhooks will rely on network controls only.",
                    id="mbongopay.W003",
                ),
            )

        if getattr(settings, "CARD_PAYMENT_PROCESSOR", "") == "mock_card_processor":
            errors.append(
                Warning(
                    "CARD_PAYMENT_PROCESSOR is using the mock processor in production.",
                    id="mbongopay.W004",
                ),
            )

        if getattr(settings, "KYC_PROVIDER", "") == "manual_kyc_review":
            errors.append(
                Warning(
                    "KYC_PROVIDER is using manual review only in production.",
                    id="mbongopay.W005",
                ),
            )

        if getattr(settings, "SANCTIONS_AML_PROVIDER", "") == "manual_sanctions_review":
            errors.append(
                Warning(
                    "SANCTIONS_AML_PROVIDER is using manual review only in production.",
                    id="mbongopay.W006",
                ),
            )

    return errors
