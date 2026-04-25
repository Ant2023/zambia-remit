from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings

from common.integrations import get_provider_config, redact_sensitive, request_json

from .models import TransferSanctionsCheck


MANUAL_SANCTIONS_PROVIDER = "manual_sanctions_review"


@dataclass(frozen=True)
class SanctionsScreeningResult:
    provider_name: str
    status: str
    status_reason: str
    screening_payload: dict
    response_payload: dict
    provider_reference: str = ""
    match_score: Decimal | None = None


class BaseSanctionsAmlProvider:
    code = ""
    display_name = ""

    def screen_party(
        self,
        *,
        party_type: str,
        screened_name: str,
        payload: dict,
        transfer_reference: str,
    ) -> SanctionsScreeningResult:
        raise NotImplementedError


class ManualSanctionsAmlProvider(BaseSanctionsAmlProvider):
    code = MANUAL_SANCTIONS_PROVIDER
    display_name = "Manual sanctions and AML review"

    def screen_party(
        self,
        *,
        party_type: str,
        screened_name: str,
        payload: dict,
        transfer_reference: str,
    ) -> SanctionsScreeningResult:
        screening_payload = {
            **payload,
            "transfer_reference": transfer_reference,
            "integration_mode": "manual_sanctions_review",
        }
        return SanctionsScreeningResult(
            provider_name=self.code,
            status=TransferSanctionsCheck.Status.QUEUED,
            status_reason="Sanctions screening queued for manual or provider review.",
            screening_payload=redact_sensitive(screening_payload),
            response_payload={"next_action": "staff_or_provider_review"},
        )


class GenericSanctionsAmlProvider(BaseSanctionsAmlProvider):
    def __init__(self, code: str):
        self.code = code
        self.config = get_provider_config(
            "SANCTIONS_AML_PROVIDER_CONFIGS",
            code,
            default_display_name=code,
        )
        self.display_name = self.config.display_name

    def screen_party(
        self,
        *,
        party_type: str,
        screened_name: str,
        payload: dict,
        transfer_reference: str,
    ) -> SanctionsScreeningResult:
        screening_payload = {
            **payload,
            "transfer_reference": transfer_reference,
            "screened_name": screened_name,
            "integration_mode": "external_sanctions_aml_provider",
            "provider_config": self.config.public_metadata(),
        }
        response_payload = {}
        status = TransferSanctionsCheck.Status.QUEUED
        provider_reference = ""
        status_reason = "Sanctions and AML screening submitted to provider handoff."
        match_score = None

        screening_path = self.config.metadata.get("screening_path")
        if screening_path:
            response_payload = request_json(
                config=self.config,
                path=str(screening_path),
                payload=screening_payload,
                method=str(self.config.metadata.get("screening_method") or "POST"),
                headers={
                    "Idempotency-Key": f"{transfer_reference}:{party_type}",
                },
            )
            status = map_screening_status(
                response_payload.get("status")
                or response_payload.get("decision")
                or response_payload.get("result"),
            )
            provider_reference = str(
                response_payload.get("id")
                or response_payload.get("case_id")
                or response_payload.get("provider_reference")
                or "",
            )
            status_reason = str(
                response_payload.get("status_reason")
                or response_payload.get("message")
                or status_reason,
            )
            match_score = parse_match_score(response_payload.get("match_score"))

        return SanctionsScreeningResult(
            provider_name=self.code,
            provider_reference=provider_reference,
            status=status,
            status_reason=status_reason,
            screening_payload=redact_sensitive(screening_payload),
            response_payload=redact_sensitive(response_payload),
            match_score=match_score,
        )


def parse_match_score(value) -> Decimal | None:
    if value in {"", None}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def map_screening_status(status_value) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized in {"clear", "approved", "pass", "passed", "no_match"}:
        return TransferSanctionsCheck.Status.CLEAR
    if normalized in {"possible_match", "review", "needs_review", "potential_match"}:
        return TransferSanctionsCheck.Status.POSSIBLE_MATCH
    if normalized in {"confirmed_match", "match", "blocked", "deny"}:
        return TransferSanctionsCheck.Status.CONFIRMED_MATCH
    if normalized in {"error", "failed"}:
        return TransferSanctionsCheck.Status.ERROR
    if normalized in {"skipped"}:
        return TransferSanctionsCheck.Status.SKIPPED
    return TransferSanctionsCheck.Status.QUEUED


def get_sanctions_aml_provider() -> BaseSanctionsAmlProvider:
    selected_provider = getattr(
        settings,
        "SANCTIONS_AML_PROVIDER",
        MANUAL_SANCTIONS_PROVIDER,
    )
    if selected_provider == MANUAL_SANCTIONS_PROVIDER:
        return ManualSanctionsAmlProvider()

    provider_configs = getattr(settings, "SANCTIONS_AML_PROVIDER_CONFIGS", {}) or {}
    if selected_provider in provider_configs:
        return GenericSanctionsAmlProvider(selected_provider)

    raise ValueError(f"Unsupported sanctions/AML provider: {selected_provider}")
