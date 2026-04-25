from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail

from .integrations import get_provider_config, redact_sensitive, request_json


DJANGO_EMAIL_BACKEND = "django_email_backend"


@dataclass(frozen=True)
class EmailSendResult:
    provider_name: str
    provider_reference: str = ""
    response_payload: dict | None = None


class BaseEmailProvider:
    code = ""
    display_name = ""

    def send_email(
        self,
        *,
        subject: str,
        body: str,
        from_email: str,
        recipient_emails: list[str],
        metadata: dict | None = None,
    ) -> EmailSendResult:
        raise NotImplementedError


class DjangoEmailBackendProvider(BaseEmailProvider):
    code = DJANGO_EMAIL_BACKEND
    display_name = "Django email backend"

    def send_email(
        self,
        *,
        subject: str,
        body: str,
        from_email: str,
        recipient_emails: list[str],
        metadata: dict | None = None,
    ) -> EmailSendResult:
        send_mail(
            subject,
            body,
            from_email,
            recipient_emails,
            fail_silently=False,
        )
        return EmailSendResult(
            provider_name=self.code,
            response_payload={"backend": settings.EMAIL_BACKEND},
        )


class GenericApiEmailProvider(BaseEmailProvider):
    def __init__(self, code: str):
        self.code = code
        self.config = get_provider_config(
            "EMAIL_SERVICE_CONFIGS",
            code,
            default_display_name=code,
        )
        self.display_name = self.config.display_name

    def send_email(
        self,
        *,
        subject: str,
        body: str,
        from_email: str,
        recipient_emails: list[str],
        metadata: dict | None = None,
    ) -> EmailSendResult:
        payload = {
            "from_email": from_email,
            "to": recipient_emails,
            "subject": subject,
            "text": body,
            "metadata": metadata or {},
        }
        response = request_json(
            config=self.config,
            path=str(self.config.metadata.get("send_path") or "/email/send"),
            payload=payload,
            method=str(self.config.metadata.get("send_method") or "POST"),
        )
        provider_reference = str(
            response.get("id")
            or response.get("message_id")
            or response.get("provider_reference")
            or "",
        )
        return EmailSendResult(
            provider_name=self.code,
            provider_reference=provider_reference,
            response_payload=redact_sensitive(response),
        )


def get_email_provider(provider_name: str | None = None) -> BaseEmailProvider:
    selected_provider = provider_name or getattr(
        settings,
        "EMAIL_SERVICE_PROVIDER",
        DJANGO_EMAIL_BACKEND,
    )
    if selected_provider == DJANGO_EMAIL_BACKEND:
        return DjangoEmailBackendProvider()

    configured_providers = getattr(settings, "EMAIL_SERVICE_CONFIGS", {}) or {}
    if selected_provider in configured_providers:
        return GenericApiEmailProvider(selected_provider)

    raise ValueError(f"Unsupported email service provider: {selected_provider}")


def send_transactional_email(
    *,
    subject: str,
    body: str,
    recipient_emails: list[str],
    from_email: str | None = None,
    metadata: dict | None = None,
) -> EmailSendResult:
    provider = get_email_provider()
    return provider.send_email(
        subject=subject,
        body=body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        recipient_emails=recipient_emails,
        metadata=metadata,
    )
