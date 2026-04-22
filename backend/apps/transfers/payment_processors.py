from __future__ import annotations

from dataclasses import dataclass
import re

from django.conf import settings

from common.security import encrypt_text

from .models import Transfer, TransferPaymentInstruction


@dataclass(frozen=True)
class PreparedPaymentInstruction:
    provider_name: str
    status: str
    instructions: dict


@dataclass(frozen=True)
class PaymentAuthorizationResult:
    status: str
    status_reason: str
    instruction_updates: dict


class BasePaymentProcessor:
    code = ""
    display_name = ""

    def prepare_instruction(
        self,
        *,
        transfer: Transfer,
        provider_reference: str,
    ) -> PreparedPaymentInstruction:
        raise NotImplementedError

    def authorize_payment(
        self,
        *,
        instruction: TransferPaymentInstruction,
        cardholder_name: str,
        card_number: str,
        expiry_month: int,
        expiry_year: int,
        cvv: str,
        billing_postal_code: str,
    ) -> PaymentAuthorizationResult:
        raise NotImplementedError


class MockCardPaymentProcessor(BasePaymentProcessor):
    code = "mock_card_processor"
    display_name = "Mock card processor"
    APPROVED_TEST_CARD = "4242424242424242"
    DECLINED_TEST_CARD = "4000000000000002"
    REVIEW_TEST_CARD = "4000000000009235"

    def prepare_instruction(
        self,
        *,
        transfer: Transfer,
        provider_reference: str,
    ) -> PreparedPaymentInstruction:
        amount = transfer.send_amount + transfer.fee_amount
        currency_code = transfer.source_currency.code
        return PreparedPaymentInstruction(
            provider_name=self.code,
            status=TransferPaymentInstruction.Status.PENDING_AUTHORIZATION,
            instructions={
                "title": "Card payment",
                "summary": (
                    "Card authorization is prepared for this transfer and ready "
                    "for processor handoff."
                ),
                "steps": [
                    "Collect card details using the processor widget or hosted flow.",
                    "Authorize the total amount before marking funding as paid.",
                    "Store the processor session or payment reference for support.",
                ],
                "processor_code": self.code,
                "processor_display_name": self.display_name,
                "integration_mode": "mock_embedded_card",
                "next_action": "authorize_card",
                "session_reference": f"CARD-{provider_reference}",
                "amount_label": f"{amount} {currency_code}",
                "reference": provider_reference,
                "supported_countries": [transfer.source_country.iso_code],
                "test_card": "4242 4242 4242 4242",
                "card_fields": [
                    {"name": "cardholder_name", "label": "Cardholder name"},
                    {"name": "card_number", "label": "Card number"},
                    {"name": "expiry_month", "label": "Expiry month"},
                    {"name": "expiry_year", "label": "Expiry year"},
                    {"name": "cvv", "label": "Security code"},
                    {"name": "billing_postal_code", "label": "Billing ZIP/postal code"},
                ],
                "test_cards": [
                    {
                        "number": "4242 4242 4242 4242",
                        "outcome": "authorized",
                        "description": "Approves the authorization flow.",
                    },
                    {
                        "number": "4000 0000 0000 0002",
                        "outcome": "failed",
                        "description": "Simulates an issuer decline.",
                    },
                    {
                        "number": "4000 0000 0000 9235",
                        "outcome": "requires_review",
                        "description": "Simulates a processor review hold.",
                    },
                ],
            },
        )

    def authorize_payment(
        self,
        *,
        instruction: TransferPaymentInstruction,
        cardholder_name: str,
        card_number: str,
        expiry_month: int,
        expiry_year: int,
        cvv: str,
        billing_postal_code: str,
    ) -> PaymentAuthorizationResult:
        normalized_card_number = re.sub(r"\D", "", card_number)
        masked_card = f"**** **** **** {normalized_card_number[-4:]}"
        base_updates = {
            "authorization_cardholder_name_encrypted": encrypt_text(cardholder_name),
            "authorization_masked_card": masked_card,
            "processor_code": self.code,
            "processor_display_name": self.display_name,
        }

        if normalized_card_number == self.APPROVED_TEST_CARD:
            return PaymentAuthorizationResult(
                status=TransferPaymentInstruction.Status.AUTHORIZED,
                status_reason="Authorization approved by mock card processor.",
                instruction_updates={
                    **base_updates,
                    "last_authorization_status": "authorized",
                    "last_authorization_message": (
                        "Authorization approved by mock card processor."
                    ),
                    "authorization_reference": f"AUTH-{instruction.provider_reference}",
                },
            )

        if normalized_card_number == self.REVIEW_TEST_CARD:
            return PaymentAuthorizationResult(
                status=TransferPaymentInstruction.Status.REQUIRES_REVIEW,
                status_reason="Authorization requires processor review.",
                instruction_updates={
                    **base_updates,
                    "last_authorization_status": "requires_review",
                    "last_authorization_message": (
                        "Authorization requires processor review."
                    ),
                    "authorization_reference": f"REV-{instruction.provider_reference}",
                },
            )

        if normalized_card_number == self.DECLINED_TEST_CARD:
            decline_message = "Card issuer declined the authorization."
        else:
            decline_message = (
                "Unsupported test card. Use one of the configured mock test cards."
            )

        return PaymentAuthorizationResult(
            status=TransferPaymentInstruction.Status.FAILED,
            status_reason=decline_message,
            instruction_updates={
                **base_updates,
                "last_authorization_status": "failed",
                "last_authorization_message": decline_message,
                "authorization_reference": f"FAIL-{instruction.provider_reference}",
            },
        )


class ManualBankTransferProcessor(BasePaymentProcessor):
    code = "manual_bank_transfer"
    display_name = "Manual bank transfer"

    def prepare_instruction(
        self,
        *,
        transfer: Transfer,
        provider_reference: str,
    ) -> PreparedPaymentInstruction:
        amount = transfer.send_amount + transfer.fee_amount
        currency_code = transfer.source_currency.code
        return PreparedPaymentInstruction(
            provider_name=self.code,
            status=TransferPaymentInstruction.Status.NOT_STARTED,
            instructions={
                "title": "Bank transfer",
                "summary": "Send a bank transfer using the details below.",
                "steps": [
                    "Use the total amount exactly.",
                    "Include the payment reference in the memo or reference field.",
                    "Bank transfers may need manual reconciliation before payout.",
                ],
                "processor_code": self.code,
                "processor_display_name": self.display_name,
                "integration_mode": "manual_bank_transfer",
                "next_action": "submit_bank_transfer",
                "bank_name": "MbongoPay Settlement Bank",
                "account_name": "MbongoPay Client Funds",
                "account_number": "000123456789",
                "routing_number": "021000021",
                "amount_label": f"{amount} {currency_code}",
                "reference": provider_reference,
            },
        )

    def authorize_payment(
        self,
        *,
        instruction: TransferPaymentInstruction,
        cardholder_name: str,
        card_number: str,
        expiry_month: int,
        expiry_year: int,
        cvv: str,
        billing_postal_code: str,
    ) -> PaymentAuthorizationResult:
        raise ValueError("Bank transfer instructions do not support card authorization.")


def get_payment_processor(payment_method: str) -> BasePaymentProcessor:
    if payment_method in {
        TransferPaymentInstruction.PaymentMethod.CREDIT_CARD,
        TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
    }:
        processor_code = getattr(
            settings,
            "CARD_PAYMENT_PROCESSOR",
            MockCardPaymentProcessor.code,
        )
        if processor_code == MockCardPaymentProcessor.code:
            return MockCardPaymentProcessor()
        raise ValueError(f"Unsupported card payment processor: {processor_code}")

    processor_code = getattr(
        settings,
        "BANK_TRANSFER_PAYMENT_PROCESSOR",
        ManualBankTransferProcessor.code,
    )
    if processor_code == ManualBankTransferProcessor.code:
        return ManualBankTransferProcessor()
    raise ValueError(f"Unsupported bank transfer processor: {processor_code}")


def get_payment_processor_by_provider(provider_name: str) -> BasePaymentProcessor:
    processors = (
        MockCardPaymentProcessor(),
        ManualBankTransferProcessor(),
    )
    for processor in processors:
        if processor.code == provider_name:
            return processor
    raise ValueError(f"Unsupported payment provider: {provider_name}")


def prepare_payment_instruction(
    transfer: Transfer,
    payment_method: str,
    provider_reference: str,
) -> PreparedPaymentInstruction:
    processor = get_payment_processor(payment_method)
    return processor.prepare_instruction(
        transfer=transfer,
        provider_reference=provider_reference,
    )


def authorize_payment_instruction(
    instruction: TransferPaymentInstruction,
    *,
    cardholder_name: str,
    card_number: str,
    expiry_month: int,
    expiry_year: int,
    cvv: str,
    billing_postal_code: str,
) -> PaymentAuthorizationResult:
    processor = get_payment_processor(instruction.payment_method)
    return processor.authorize_payment(
        instruction=instruction,
        cardholder_name=cardholder_name,
        card_number=card_number,
        expiry_month=expiry_month,
        expiry_year=expiry_year,
        cvv=cvv,
        billing_postal_code=billing_postal_code,
    )
