from dataclasses import dataclass
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from django.conf import settings
from rest_framework import serializers

from common.choices import PayoutMethod
from common.integrations import (
    ProviderConfigurationError,
    ProviderRequestError,
    get_provider_config,
    redact_sensitive,
    request_json,
)

from .models import Transfer, TransferPayoutAttempt


@dataclass(frozen=True)
class PayoutSubmissionResult:
    status: str
    provider_status: str
    status_reason: str
    request_payload: dict
    response_payload: dict


@dataclass(frozen=True)
class PayoutReversalResult:
    status: str
    provider_status: str
    status_reason: str
    response_payload: dict


@dataclass(frozen=True)
class PayoutStatusResult:
    status: str
    provider_status: str
    status_reason: str
    response_payload: dict
    provider_event_id: str = ""


class BasePayoutProcessor:
    code = ""
    display_name = ""
    payout_method = ""

    def submit_payout(
        self,
        *,
        transfer: Transfer,
        attempt: TransferPayoutAttempt,
    ) -> PayoutSubmissionResult:
        raise NotImplementedError

    def reverse_payout(
        self,
        *,
        attempt: TransferPayoutAttempt,
        note: str,
    ) -> PayoutReversalResult:
        raise NotImplementedError

    def get_payout_status(
        self,
        *,
        attempt: TransferPayoutAttempt,
    ) -> PayoutStatusResult:
        raise NotImplementedError

    def build_common_payload(
        self,
        *,
        transfer: Transfer,
        attempt: TransferPayoutAttempt,
    ) -> dict:
        return {
            "transfer_reference": transfer.reference,
            "payout_reference": attempt.provider_reference,
            "provider_code": self.code,
            "provider_display_name": self.display_name,
            "payout_method": transfer.payout_method,
            "amount": str(attempt.amount),
            "currency": attempt.currency.code,
            "source_country": transfer.source_country.iso_code,
            "destination_country": transfer.destination_country.iso_code,
            "recipient": {
                "id": str(transfer.recipient_id),
                "name": (
                    f"{transfer.recipient.first_name} "
                    f"{transfer.recipient.last_name}"
                ).strip(),
                "phone_number": transfer.recipient.phone_number,
            },
        }


class InternalMobileMoneyPayoutProcessor(BasePayoutProcessor):
    code = "internal_mobile_money"
    display_name = "Internal mobile money operations"
    payout_method = PayoutMethod.MOBILE_MONEY

    def submit_payout(
        self,
        *,
        transfer: Transfer,
        attempt: TransferPayoutAttempt,
    ) -> PayoutSubmissionResult:
        account = (
            transfer.recipient.mobile_money_accounts.filter(is_default=True).first()
            or transfer.recipient.mobile_money_accounts.first()
        )
        if account is None:
            raise serializers.ValidationError(
                {"recipient_id": "Recipient needs a mobile money account."},
            )

        request_payload = {
            **self.build_common_payload(transfer=transfer, attempt=attempt),
            "mobile_money": {
                "provider_name": account.provider_name,
                "mobile_number": account.mobile_number,
                "account_name": account.account_name,
            },
            "integration_mode": "internal_mobile_money_queue",
        }
        return PayoutSubmissionResult(
            status=TransferPayoutAttempt.Status.SUBMITTED,
            provider_status="submitted",
            status_reason="Mobile money payout submitted to internal operations queue.",
            request_payload=request_payload,
            response_payload={
                "provider_reference": attempt.provider_reference,
                "next_action": "await_provider_status",
                "provider_status": "submitted",
            },
        )

    def reverse_payout(
        self,
        *,
        attempt: TransferPayoutAttempt,
        note: str,
    ) -> PayoutReversalResult:
        return PayoutReversalResult(
            status=TransferPayoutAttempt.Status.REVERSED,
            provider_status="reversed",
            status_reason=note or "Mobile money payout reversal recorded.",
            response_payload={
                "provider_reference": attempt.provider_reference,
                "reversal_mode": "internal_manual",
            },
        )

    def get_payout_status(
        self,
        *,
        attempt: TransferPayoutAttempt,
    ) -> PayoutStatusResult:
        return PayoutStatusResult(
            status=attempt.status,
            provider_status=attempt.provider_status or attempt.status,
            status_reason=attempt.status_reason or "Awaiting internal operations update.",
            response_payload={
                "provider_reference": attempt.provider_reference,
                "sync_mode": "internal_manual",
            },
        )


class InternalBankDepositPayoutProcessor(BasePayoutProcessor):
    code = "internal_bank_deposit"
    display_name = "Internal bank deposit operations"
    payout_method = PayoutMethod.BANK_DEPOSIT

    def submit_payout(
        self,
        *,
        transfer: Transfer,
        attempt: TransferPayoutAttempt,
    ) -> PayoutSubmissionResult:
        account = (
            transfer.recipient.bank_accounts.filter(is_default=True).first()
            or transfer.recipient.bank_accounts.first()
        )
        if account is None:
            raise serializers.ValidationError(
                {"recipient_id": "Recipient needs a bank account."},
            )

        request_payload = {
            **self.build_common_payload(transfer=transfer, attempt=attempt),
            "bank_account": {
                "bank_name": account.bank_name,
                "account_number": account.account_number,
                "account_name": account.account_name,
                "branch_name": account.branch_name,
                "swift_code": account.swift_code,
            },
            "integration_mode": "internal_bank_deposit_queue",
        }
        return PayoutSubmissionResult(
            status=TransferPayoutAttempt.Status.SUBMITTED,
            provider_status="submitted",
            status_reason="Bank deposit payout submitted to internal operations queue.",
            request_payload=request_payload,
            response_payload={
                "provider_reference": attempt.provider_reference,
                "next_action": "await_provider_status",
                "provider_status": "submitted",
            },
        )

    def reverse_payout(
        self,
        *,
        attempt: TransferPayoutAttempt,
        note: str,
    ) -> PayoutReversalResult:
        return PayoutReversalResult(
            status=TransferPayoutAttempt.Status.REVERSED,
            provider_status="reversed",
            status_reason=note or "Bank deposit payout reversal recorded.",
            response_payload={
                "provider_reference": attempt.provider_reference,
                "reversal_mode": "internal_manual",
            },
        )

    def get_payout_status(
        self,
        *,
        attempt: TransferPayoutAttempt,
    ) -> PayoutStatusResult:
        return PayoutStatusResult(
            status=attempt.status,
            provider_status=attempt.provider_status or attempt.status,
            status_reason=attempt.status_reason or "Awaiting internal operations update.",
            response_payload={
                "provider_reference": attempt.provider_reference,
                "sync_mode": "internal_manual",
            },
        )


class GenericExternalPayoutProcessor(BasePayoutProcessor):
    def __init__(
        self,
        *,
        provider_code: str,
        display_name: str = "",
        payout_method: str = "",
        provider_metadata: dict | None = None,
    ):
        self.code = provider_code
        self.config = get_provider_config(
            "PAYOUT_PROVIDER_CONFIGS",
            provider_code,
            default_display_name=display_name or provider_code,
            defaults=provider_metadata or {},
        )
        self.display_name = self.config.display_name
        self.payout_method = payout_method or str(
            self.config.metadata.get("payout_method") or "",
        )

    def build_destination_details(self, transfer: Transfer) -> dict:
        if transfer.payout_method == PayoutMethod.MOBILE_MONEY:
            account = (
                transfer.recipient.mobile_money_accounts.filter(is_default=True).first()
                or transfer.recipient.mobile_money_accounts.first()
            )
            if account is None:
                raise serializers.ValidationError(
                    {"recipient_id": "Recipient needs a mobile money account."},
                )
            return {
                "mobile_money": {
                    "provider_name": account.provider_name,
                    "mobile_number": account.mobile_number,
                    "account_name": account.account_name,
                },
            }

        if transfer.payout_method == PayoutMethod.BANK_DEPOSIT:
            account = (
                transfer.recipient.bank_accounts.filter(is_default=True).first()
                or transfer.recipient.bank_accounts.first()
            )
            if account is None:
                raise serializers.ValidationError(
                    {"recipient_id": "Recipient needs a bank account."},
                )
            return {
                "bank_account": {
                    "bank_name": account.bank_name,
                    "account_number": account.account_number,
                    "account_name": account.account_name,
                    "branch_name": account.branch_name,
                    "swift_code": account.swift_code,
                },
            }

        raise serializers.ValidationError(
            {"payout_method": "Unsupported payout method for this provider."},
        )

    def submit_payout(
        self,
        *,
        transfer: Transfer,
        attempt: TransferPayoutAttempt,
    ) -> PayoutSubmissionResult:
        request_payload = {
            **self.build_common_payload(transfer=transfer, attempt=attempt),
            **self.build_destination_details(transfer),
            "integration_mode": "external_payout_provider",
            "provider_config": self.config.public_metadata(),
        }
        provider_response = {}
        provider_status = "submitted"
        status_reason = "Payout submitted to external provider handoff."

        submit_path = self.config.metadata.get("submit_path")
        if submit_path:
            provider_response = request_json(
                config=self.config,
                path=str(submit_path),
                payload=request_payload,
                method=str(self.config.metadata.get("submit_method") or "POST"),
                headers={"Idempotency-Key": attempt.provider_reference},
            )
            provider_status = str(provider_response.get("status") or provider_status)
            status_reason = str(
                provider_response.get("status_reason")
                or provider_response.get("message")
                or status_reason,
            )

        return PayoutSubmissionResult(
            status=TransferPayoutAttempt.Status.SUBMITTED,
            provider_status=provider_status,
            status_reason=status_reason,
            request_payload=redact_sensitive(request_payload),
            response_payload={
                "provider_reference": str(
                    provider_response.get("id")
                    or provider_response.get("payout_id")
                    or attempt.provider_reference,
                ),
                "next_action": "await_provider_status",
                "provider_status": provider_status,
                "provider_response": redact_sensitive(provider_response),
            },
        )

    def reverse_payout(
        self,
        *,
        attempt: TransferPayoutAttempt,
        note: str,
    ) -> PayoutReversalResult:
        provider_response = {}
        provider_status = "reversed"
        status_reason = note or "Payout reversal submitted to external provider."
        reverse_path = self.config.metadata.get("reverse_path")
        if reverse_path:
            provider_response = request_json(
                config=self.config,
                path=str(reverse_path),
                payload={
                    "payout_reference": attempt.provider_reference,
                    "provider_code": self.code,
                    "reason": note,
                },
                method=str(self.config.metadata.get("reverse_method") or "POST"),
            )
            provider_status = str(provider_response.get("status") or provider_status)
            status_reason = str(
                provider_response.get("status_reason")
                or provider_response.get("message")
                or status_reason,
            )

        return PayoutReversalResult(
            status=TransferPayoutAttempt.Status.REVERSED,
            provider_status=provider_status,
            status_reason=status_reason,
            response_payload={
                "provider_reference": attempt.provider_reference,
                "reversal_mode": "external_provider",
                "provider_response": redact_sensitive(provider_response),
            },
        )

    def get_payout_status(
        self,
        *,
        attempt: TransferPayoutAttempt,
    ) -> PayoutStatusResult:
        status_path = self.config.metadata.get("status_path")
        if not status_path:
            return PayoutStatusResult(
                status=attempt.status,
                provider_status=attempt.provider_status or attempt.status,
                status_reason=(
                    attempt.status_reason
                    or "Provider status polling is not configured for this provider."
                ),
                response_payload={
                    "provider_reference": attempt.provider_reference,
                    "sync_mode": "manual",
                },
            )

        provider_response = request_json(
            config=self.config,
            path=str(status_path).format(
                provider_reference=attempt.provider_reference,
            ),
            payload=None,
            method=str(self.config.metadata.get("status_method") or "GET"),
        )
        provider_status = str(provider_response.get("status") or attempt.provider_status)
        return PayoutStatusResult(
            status=str(
                provider_response.get("payout_status")
                or provider_response.get("mapped_status")
                or attempt.status,
            ),
            provider_status=provider_status,
            status_reason=str(
                provider_response.get("status_reason")
                or provider_response.get("message")
                or attempt.status_reason
                or "Provider status synced.",
            ),
            provider_event_id=str(
                provider_response.get("event_id")
                or provider_response.get("id")
                or provider_response.get("transaction_id")
                or "",
            ),
            response_payload={
                "provider_reference": attempt.provider_reference,
                "provider_response": redact_sensitive(provider_response),
                "sync_mode": "external_provider",
            },
        )


class MtnMomoPayoutProcessor(BasePayoutProcessor):
    code = "mtn_momo"
    display_name = "MTN MoMo"
    payout_method = PayoutMethod.MOBILE_MONEY

    STATUS_MAP = {
        "SUCCESSFUL": TransferPayoutAttempt.Status.PAID_OUT,
        "SUCCESS": TransferPayoutAttempt.Status.PAID_OUT,
        "COMPLETED": TransferPayoutAttempt.Status.PAID_OUT,
        "PENDING": TransferPayoutAttempt.Status.PROCESSING,
        "PROCESSING": TransferPayoutAttempt.Status.PROCESSING,
        "FAILED": TransferPayoutAttempt.Status.FAILED,
        "REJECTED": TransferPayoutAttempt.Status.FAILED,
        "TIMEOUT": TransferPayoutAttempt.Status.FAILED,
    }

    def __init__(self, *, provider=None):
        provider_metadata = getattr(provider, "metadata", {}) if provider is not None else {}
        self.config = get_provider_config(
            "PAYOUT_PROVIDER_CONFIGS",
            self.code,
            default_display_name=getattr(provider, "name", self.display_name),
            defaults=provider_metadata or {},
        )
        self.display_name = self.config.display_name

    def _metadata_value(self, key: str, default: str = "") -> str:
        return str(self.config.metadata.get(key) or default).strip()

    def _required_metadata_value(self, key: str) -> str:
        value = self._metadata_value(key)
        if not value:
            raise ProviderConfigurationError(f"{self.code} requires {key}.")
        return value

    def _subscription_key(self) -> str:
        return self.config.api_key or self._metadata_value("subscription_key")

    def _target_environment(self) -> str:
        return self._metadata_value("target_environment", "sandbox")

    def _endpoint_url(self, path: str) -> str:
        return self.config.url_for(path)

    def _request_json(
        self,
        *,
        path: str,
        method: str,
        payload: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self._subscription_key(),
            "X-Target-Environment": self._target_environment(),
            **(headers or {}),
        }
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self._endpoint_url(path),
            data=data,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ProviderRequestError(
                f"{self.code} returned HTTP {exc.code}: {error_body}",
            ) from exc
        except URLError as exc:
            raise ProviderRequestError(f"{self.code} request failed: {exc}") from exc
        except TimeoutError as exc:
            raise ProviderRequestError(f"{self.code} request timed out.") from exc

        if not response_body:
            return {}
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError:
            return {"raw": response_body}
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    def _access_token(self) -> str:
        user_id = self._required_metadata_value("user_id")
        api_secret = self._required_metadata_value("api_secret")
        subscription_key = self._subscription_key()
        if not subscription_key:
            raise ProviderConfigurationError(f"{self.code} requires api_key.")

        credentials = f"{user_id}:{api_secret}".encode("utf-8")
        authorization = base64.b64encode(credentials).decode("ascii")
        response = self._request_json(
            path=self._metadata_value("token_path", "/disbursement/token/"),
            method="POST",
            headers={
                "Authorization": f"Basic {authorization}",
                "X-Target-Environment": self._target_environment(),
            },
        )
        access_token = str(response.get("access_token") or "").strip()
        if not access_token:
            raise ProviderRequestError(f"{self.code} token response did not include access_token.")
        return access_token

    def _ensure_mtn_reference(self, attempt: TransferPayoutAttempt) -> str:
        try:
            UUID(str(attempt.provider_reference), version=4)
            return attempt.provider_reference
        except ValueError:
            pass

        attempt.provider_reference = str(attempt.id)
        attempt.save(update_fields=("provider_reference", "updated_at"))
        return attempt.provider_reference

    def _mobile_money_account(self, transfer: Transfer):
        account = (
            transfer.recipient.mobile_money_accounts.filter(is_default=True).first()
            or transfer.recipient.mobile_money_accounts.first()
        )
        if account is None:
            raise serializers.ValidationError(
                {"recipient_id": "Recipient needs a mobile money account."},
            )
        return account

    def _normalize_msisdn(self, mobile_number: str) -> str:
        return "".join(character for character in mobile_number if character.isdigit())

    def _build_transfer_payload(
        self,
        *,
        transfer: Transfer,
        attempt: TransferPayoutAttempt,
    ) -> dict:
        account = self._mobile_money_account(transfer)
        currency_code = self._metadata_value("currency", attempt.currency.code)
        payload = {
            "amount": str(attempt.amount),
            "currency": currency_code,
            "externalId": transfer.reference,
            "payee": {
                "partyIdType": self._metadata_value("party_id_type", "MSISDN"),
                "partyId": self._normalize_msisdn(account.mobile_number),
            },
            "payerMessage": self._metadata_value(
                "payer_message",
                f"MbongoPay transfer {transfer.reference}",
            ),
            "payeeNote": self._metadata_value(
                "payee_note",
                f"MbongoPay payout {transfer.reference}",
            ),
        }
        transfer_type = self._metadata_value("transfer_type")
        if transfer_type:
            payload["transferType"] = transfer_type
        return payload

    def _mtn_status_to_attempt_status(self, provider_status: str) -> str:
        normalized_status = provider_status.strip().upper()
        return self.STATUS_MAP.get(normalized_status, TransferPayoutAttempt.Status.PROCESSING)

    def _status_reason(self, provider_status: str, provider_response: dict) -> str:
        reason = provider_response.get("reason") or provider_response.get("message")
        if isinstance(reason, dict):
            reason = reason.get("message") or reason.get("code")
        return str(reason or f"MTN MoMo status: {provider_status or 'submitted'}.")

    def submit_payout(
        self,
        *,
        transfer: Transfer,
        attempt: TransferPayoutAttempt,
    ) -> PayoutSubmissionResult:
        mtn_reference = self._ensure_mtn_reference(attempt)
        payout_payload = self._build_transfer_payload(transfer=transfer, attempt=attempt)
        request_payload = {
            **self.build_common_payload(transfer=transfer, attempt=attempt),
            "integration_mode": "mtn_momo_disbursement",
            "mtn": {
                "target_environment": self._target_environment(),
                "reference_id": mtn_reference,
                "transfer_path": self._metadata_value(
                    "transfer_path",
                    "/disbursement/v1_0/transfer",
                ),
                "payload": payout_payload,
            },
            "provider_config": self.config.public_metadata(),
        }

        try:
            access_token = self._access_token()
            provider_response = self._request_json(
                path=self._metadata_value("transfer_path", "/disbursement/v1_0/transfer"),
                method="POST",
                payload=payout_payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Reference-Id": mtn_reference,
                },
            )
        except (ProviderConfigurationError, ProviderRequestError) as exc:
            return PayoutSubmissionResult(
                status=TransferPayoutAttempt.Status.FAILED,
                provider_status="submission_failed",
                status_reason=str(exc),
                request_payload=redact_sensitive(request_payload),
                response_payload={
                    "provider_reference": mtn_reference,
                    "provider_transaction_id": "",
                    "provider_status": "submission_failed",
                    "provider_error": str(exc),
                    "next_action": "retry_or_manual_review",
                },
            )

        provider_status = str(provider_response.get("status") or "PENDING")
        return PayoutSubmissionResult(
            status=self._mtn_status_to_attempt_status(provider_status),
            provider_status=provider_status,
            status_reason=self._status_reason(provider_status, provider_response),
            request_payload=redact_sensitive(request_payload),
            response_payload={
                "provider_reference": mtn_reference,
                "provider_transaction_id": str(
                    provider_response.get("financialTransactionId")
                    or provider_response.get("transactionId")
                    or "",
                ),
                "next_action": "await_provider_status",
                "provider_status": provider_status,
                "provider_response": redact_sensitive(provider_response),
            },
        )

    def get_payout_status(
        self,
        *,
        attempt: TransferPayoutAttempt,
    ) -> PayoutStatusResult:
        try:
            access_token = self._access_token()
            provider_response = self._request_json(
                path=(
                    f"{self._metadata_value('transfer_path', '/disbursement/v1_0/transfer')}"
                    f"/{attempt.provider_reference}"
                ),
                method="GET",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except (ProviderConfigurationError, ProviderRequestError) as exc:
            return PayoutStatusResult(
                status=attempt.status,
                provider_status="status_sync_failed",
                status_reason=str(exc),
                provider_event_id=f"mtn-status-sync-failed-{attempt.provider_reference}",
                response_payload={
                    "provider_reference": attempt.provider_reference,
                    "provider_error": str(exc),
                    "sync_mode": "mtn_momo_status_poll",
                },
            )

        provider_status = str(provider_response.get("status") or attempt.provider_status)
        transaction_id = str(provider_response.get("financialTransactionId") or "")
        return PayoutStatusResult(
            status=self._mtn_status_to_attempt_status(provider_status),
            provider_status=provider_status,
            status_reason=self._status_reason(provider_status, provider_response),
            provider_event_id=transaction_id or f"mtn-status-{attempt.provider_reference}-{provider_status}",
            response_payload={
                "provider_reference": attempt.provider_reference,
                "provider_transaction_id": transaction_id,
                "provider_response": redact_sensitive(provider_response),
                "sync_mode": "mtn_momo_status_poll",
            },
        )

    def reverse_payout(
        self,
        *,
        attempt: TransferPayoutAttempt,
        note: str,
    ) -> PayoutReversalResult:
        return PayoutReversalResult(
            status=TransferPayoutAttempt.Status.REVERSED,
            provider_status="manual_reversal_required",
            status_reason=note or "MTN MoMo payout reversal requires operations review.",
            response_payload={
                "provider_reference": attempt.provider_reference,
                "reversal_mode": "manual_mtn_momo_operations",
            },
        )


def get_payout_processor(provider_code: str, provider=None) -> BasePayoutProcessor:
    if provider_code == MtnMomoPayoutProcessor.code:
        return MtnMomoPayoutProcessor(provider=provider)

    processors = (
        InternalMobileMoneyPayoutProcessor(),
        InternalBankDepositPayoutProcessor(),
    )
    for processor in processors:
        if processor.code == provider_code:
            return processor

    provider_configs = getattr(settings, "PAYOUT_PROVIDER_CONFIGS", {}) or {}
    provider_metadata = getattr(provider, "metadata", {}) if provider is not None else {}
    if provider_code in provider_configs or provider_metadata.get("processor") == "external":
        return GenericExternalPayoutProcessor(
            provider_code=provider_code,
            display_name=getattr(provider, "name", provider_code),
            payout_method=getattr(provider, "payout_method", ""),
            provider_metadata=provider_metadata,
        )

    raise serializers.ValidationError(
        {"payout_provider": f"Unsupported payout provider: {provider_code}"},
    )
