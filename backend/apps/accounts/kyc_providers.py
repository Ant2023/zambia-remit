from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from common.integrations import get_provider_config, redact_sensitive, request_json

from .models import SenderKycCheck, SenderProfile


MANUAL_KYC_PROVIDER = "manual_kyc_review"


@dataclass(frozen=True)
class KycSubmissionResult:
    provider_name: str
    status: str
    status_reason: str
    request_payload: dict
    response_payload: dict
    provider_reference: str = ""


class BaseKycProvider:
    code = ""
    display_name = ""

    def submit_check(self, profile: SenderProfile) -> KycSubmissionResult:
        raise NotImplementedError

    def build_payload(self, profile: SenderProfile) -> dict:
        return {
            "sender_profile_id": str(profile.id),
            "user_id": str(profile.user_id),
            "email": profile.user.email,
            "first_name": profile.user.first_name,
            "last_name": profile.user.last_name,
            "phone_number": profile.phone_number,
            "country": profile.country.iso_code if profile.country_id else "",
            "date_of_birth": profile.date_of_birth.isoformat()
            if profile.date_of_birth
            else "",
            "address": {
                "address_line_1": profile.address_line_1,
                "address_line_2": profile.address_line_2,
                "city": profile.city,
                "region": profile.region,
                "postal_code": profile.postal_code,
            },
        }


class ManualKycProvider(BaseKycProvider):
    code = MANUAL_KYC_PROVIDER
    display_name = "Manual KYC review"

    def submit_check(self, profile: SenderProfile) -> KycSubmissionResult:
        request_payload = self.build_payload(profile)
        return KycSubmissionResult(
            provider_name=self.code,
            status=SenderKycCheck.Status.SKIPPED,
            status_reason="KYC is queued for manual staff review.",
            request_payload=redact_sensitive(request_payload),
            response_payload={
                "integration_mode": "manual_review",
                "next_action": "staff_review",
            },
        )


class GenericKycProvider(BaseKycProvider):
    def __init__(self, code: str):
        self.code = code
        self.config = get_provider_config(
            "KYC_PROVIDER_CONFIGS",
            code,
            default_display_name=code,
        )
        self.display_name = self.config.display_name

    def submit_check(self, profile: SenderProfile) -> KycSubmissionResult:
        request_payload = {
            **self.build_payload(profile),
            "integration_mode": "external_kyc_provider",
            "provider_config": self.config.public_metadata(),
        }
        response_payload = {}
        status = SenderKycCheck.Status.SUBMITTED
        status_reason = "KYC submitted to external provider handoff."
        provider_reference = ""

        submit_path = self.config.metadata.get("submit_path")
        if submit_path:
            response_payload = request_json(
                config=self.config,
                path=str(submit_path),
                payload=request_payload,
                method=str(self.config.metadata.get("submit_method") or "POST"),
                headers={"Idempotency-Key": str(profile.id)},
            )
            provider_reference = str(
                response_payload.get("id")
                or response_payload.get("case_id")
                or response_payload.get("provider_reference")
                or "",
            )
            status = map_provider_status(response_payload.get("status"))
            status_reason = str(
                response_payload.get("status_reason")
                or response_payload.get("message")
                or status_reason,
            )

        return KycSubmissionResult(
            provider_name=self.code,
            provider_reference=provider_reference,
            status=status,
            status_reason=status_reason,
            request_payload=redact_sensitive(request_payload),
            response_payload=redact_sensitive(response_payload),
        )


def map_provider_status(status_value) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized in {"approved", "clear", "passed", "verified"}:
        return SenderKycCheck.Status.CLEAR
    if normalized in {"declined", "failed", "rejected"}:
        return SenderKycCheck.Status.REJECTED
    if normalized in {"review", "needs_review", "manual_review"}:
        return SenderKycCheck.Status.NEEDS_REVIEW
    if normalized in {"error", "errored"}:
        return SenderKycCheck.Status.ERROR
    return SenderKycCheck.Status.SUBMITTED


def get_kyc_provider() -> BaseKycProvider:
    selected_provider = getattr(settings, "KYC_PROVIDER", MANUAL_KYC_PROVIDER)
    if selected_provider == MANUAL_KYC_PROVIDER:
        return ManualKycProvider()

    provider_configs = getattr(settings, "KYC_PROVIDER_CONFIGS", {}) or {}
    if selected_provider in provider_configs:
        return GenericKycProvider(selected_provider)

    raise ValueError(f"Unsupported KYC provider: {selected_provider}")


def request_sender_kyc_check(profile: SenderProfile) -> SenderKycCheck:
    provider = get_kyc_provider()
    result = provider.submit_check(profile)
    now = timezone.now()
    completed_at = None
    if result.status in {
        SenderKycCheck.Status.CLEAR,
        SenderKycCheck.Status.NEEDS_REVIEW,
        SenderKycCheck.Status.REJECTED,
        SenderKycCheck.Status.ERROR,
        SenderKycCheck.Status.SKIPPED,
    }:
        completed_at = now

    return SenderKycCheck.objects.create(
        sender_profile=profile,
        provider_name=result.provider_name,
        provider_reference=result.provider_reference,
        status=result.status,
        request_payload=result.request_payload,
        response_payload=result.response_payload,
        status_reason=result.status_reason,
        submitted_at=now,
        completed_at=completed_at,
        error=result.status_reason if result.status == SenderKycCheck.Status.ERROR else "",
    )
