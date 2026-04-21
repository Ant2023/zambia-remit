from dataclasses import dataclass

from rest_framework import serializers

from common.choices import PayoutMethod

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


def get_payout_processor(provider_code: str) -> BasePayoutProcessor:
    processors = (
        InternalMobileMoneyPayoutProcessor(),
        InternalBankDepositPayoutProcessor(),
    )
    for processor in processors:
        if processor.code == provider_code:
            return processor
    raise serializers.ValidationError(
        {"payout_provider": f"Unsupported payout provider: {provider_code}"},
    )
