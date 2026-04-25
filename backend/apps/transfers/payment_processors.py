from __future__ import annotations

from dataclasses import dataclass
import re

from django.conf import settings
from rest_framework import serializers

from common.integrations import get_provider_config, redact_sensitive, request_json
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


class StripePaymentProcessor(BasePaymentProcessor):
    code = "stripe"
    display_name = "Stripe"

    def _load_stripe(self):
        try:
            import stripe  # noqa: PLC0415
        except ImportError as exc:
            raise serializers.ValidationError(
                {
                    "payment_method": (
                        "Stripe payments are not installed on the backend. "
                        "Redeploy the backend after installing dependencies."
                    ),
                },
            ) from exc

        if not settings.STRIPE_SECRET_KEY:
            raise serializers.ValidationError(
                {"payment_method": "Stripe secret key is not configured."},
            )

        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe

    def _raise_stripe_error(self, exc: Exception) -> None:
        if exc.__class__.__module__.startswith("stripe"):
            raise serializers.ValidationError(
                {
                    "payment_method": (
                        "Stripe is unavailable or rejected the payment setup. "
                        "Check the backend Stripe key and try again."
                    ),
                },
            ) from exc
        raise exc

    def prepare_instruction(
        self,
        *,
        transfer: Transfer,
        provider_reference: str,
    ) -> PreparedPaymentInstruction:
        stripe = self._load_stripe()
        amount = transfer.send_amount + transfer.fee_amount
        currency_code = transfer.source_currency.code.lower()
        amount_in_cents = int(amount * 100)

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_in_cents,
                currency=currency_code,
                metadata={
                    "transfer_id": str(transfer.id),
                    "transfer_reference": transfer.reference,
                    "payment_reference": provider_reference,
                    "sender_id": str(transfer.sender_id),
                },
                idempotency_key=provider_reference,
            )
        except Exception as exc:
            self._raise_stripe_error(exc)

        return PreparedPaymentInstruction(
            provider_name=self.code,
            status=TransferPaymentInstruction.Status.PENDING_AUTHORIZATION,
            instructions={
                "title": "Card payment",
                "summary": "Complete your card payment securely via Stripe.",
                "processor_code": self.code,
                "processor_display_name": self.display_name,
                "integration_mode": "stripe_payment_element",
                "next_action": "confirm_stripe_payment",
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "amount_label": f"{amount} {currency_code.upper()}",
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
        raise serializers.ValidationError(
            {
                "payment_method": (
                    "Stripe payments are confirmed client-side via Stripe.js. "
                    "Use the stripe-confirm endpoint after the client confirms."
                )
            },
        )

    def verify_payment_intent(
        self,
        *,
        instruction: TransferPaymentInstruction,
    ) -> PaymentAuthorizationResult:
        stripe = self._load_stripe()
        payment_intent_id = instruction.instructions.get("payment_intent_id", "")

        if not payment_intent_id:
            return PaymentAuthorizationResult(
                status=TransferPaymentInstruction.Status.FAILED,
                status_reason="No Stripe PaymentIntent ID found on this instruction.",
                instruction_updates={
                    "processor_code": self.code,
                    "processor_display_name": self.display_name,
                    "last_authorization_status": "failed",
                    "last_authorization_message": "Missing payment_intent_id.",
                },
            )

        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        except Exception as exc:
            self._raise_stripe_error(exc)

        if intent.status == "succeeded":
            return PaymentAuthorizationResult(
                status=TransferPaymentInstruction.Status.AUTHORIZED,
                status_reason="Stripe payment confirmed successfully.",
                instruction_updates={
                    "processor_code": self.code,
                    "processor_display_name": self.display_name,
                    "last_authorization_status": "authorized",
                    "last_authorization_message": "Stripe payment confirmed.",
                    "authorization_reference": payment_intent_id,
                },
            )

        if intent.status in {"requires_payment_method", "canceled"}:
            return PaymentAuthorizationResult(
                status=TransferPaymentInstruction.Status.FAILED,
                status_reason=f"Stripe payment failed with status: {intent.status}.",
                instruction_updates={
                    "processor_code": self.code,
                    "processor_display_name": self.display_name,
                    "last_authorization_status": "failed",
                    "last_authorization_message": f"Stripe status: {intent.status}",
                    "authorization_reference": payment_intent_id,
                },
            )

        return PaymentAuthorizationResult(
            status=TransferPaymentInstruction.Status.REQUIRES_REVIEW,
            status_reason=f"Stripe payment has unexpected status: {intent.status}.",
            instruction_updates={
                "processor_code": self.code,
                "processor_display_name": self.display_name,
                "last_authorization_status": "requires_review",
                "last_authorization_message": f"Stripe status: {intent.status}",
                "authorization_reference": payment_intent_id,
            },
        )


class GenericPaymentProcessor(BasePaymentProcessor):
    def __init__(self, code: str, payment_method: str = ""):
        self.code = code
        self.payment_method = payment_method
        self.config = get_provider_config(
            "PAYMENT_PROVIDER_CONFIGS",
            code,
            default_display_name=code,
        )
        self.display_name = self.config.display_name

    def prepare_instruction(
        self,
        *,
        transfer: Transfer,
        provider_reference: str,
    ) -> PreparedPaymentInstruction:
        amount = transfer.send_amount + transfer.fee_amount
        currency_code = transfer.source_currency.code
        request_payload = {
            "transfer_id": str(transfer.id),
            "transfer_reference": transfer.reference,
            "payment_reference": provider_reference,
            "amount": str(amount),
            "currency": currency_code,
            "payment_method": self.payment_method,
            "payer": {
                "id": str(transfer.sender_id),
                "email": transfer.sender.email,
                "name": f"{transfer.sender.first_name} {transfer.sender.last_name}".strip(),
            },
            "metadata": {
                "destination_country": transfer.destination_country.iso_code,
                "recipient_id": str(transfer.recipient_id),
            },
        }
        provider_response = {}
        checkout_url = str(self.config.metadata.get("checkout_url") or "")
        provider_session_reference = f"{self.code}-{provider_reference}"
        provider_status = "pending_provider_handoff"

        create_session_path = self.config.metadata.get("create_session_path")
        if create_session_path:
            provider_response = request_json(
                config=self.config,
                path=str(create_session_path),
                payload=request_payload,
                method=str(self.config.metadata.get("create_session_method") or "POST"),
                headers={"Idempotency-Key": provider_reference},
            )
            checkout_url = str(
                provider_response.get("checkout_url")
                or provider_response.get("url")
                or checkout_url,
            )
            provider_session_reference = str(
                provider_response.get("id")
                or provider_response.get("session_id")
                or provider_response.get("provider_reference")
                or provider_session_reference,
            )
            provider_status = str(provider_response.get("status") or "created")

        is_card = self.payment_method in {
            TransferPaymentInstruction.PaymentMethod.CREDIT_CARD,
            TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
        }
        integration_mode = str(
            self.config.metadata.get("integration_mode")
            or ("hosted_card_checkout" if is_card else "external_payment_provider"),
        )
        return PreparedPaymentInstruction(
            provider_name=self.code,
            status=(
                TransferPaymentInstruction.Status.PENDING_AUTHORIZATION
                if is_card
                else TransferPaymentInstruction.Status.NOT_STARTED
            ),
            instructions={
                "title": str(self.config.metadata.get("title") or "External payment"),
                "summary": (
                    "Payment is prepared for provider handoff and should be "
                    "confirmed by the payment webhook."
                ),
                "steps": [
                    "Send the customer through the configured provider flow.",
                    "Use the payment reference for idempotency and reconciliation.",
                    "Wait for the provider webhook before marking funding received.",
                ],
                "processor_code": self.code,
                "processor_display_name": self.display_name,
                "integration_mode": integration_mode,
                "next_action": "redirect_to_provider" if checkout_url else "await_provider_session",
                "checkout_url": checkout_url,
                "session_reference": provider_session_reference,
                "provider_status": provider_status,
                "provider_config": self.config.public_metadata(),
                "provider_response": redact_sensitive(provider_response),
                "request_payload": redact_sensitive(request_payload),
                "amount_label": f"{amount} {currency_code}",
                "reference": provider_reference,
                "requires_provider_webhook": True,
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
        raise serializers.ValidationError(
            {
                "payment_method": (
                    "This payment provider uses hosted authorization and provider "
                    "webhooks; raw card authorization is not accepted here."
                )
            },
        )


def get_configured_payment_processor(
    processor_code: str,
    *,
    payment_method: str = "",
) -> BasePaymentProcessor:
    processors = {
        MockCardPaymentProcessor.code: MockCardPaymentProcessor,
        ManualBankTransferProcessor.code: ManualBankTransferProcessor,
        StripePaymentProcessor.code: StripePaymentProcessor,
    }
    processor_class = processors.get(processor_code)
    if processor_class:
        return processor_class()

    provider_configs = getattr(settings, "PAYMENT_PROVIDER_CONFIGS", {}) or {}
    if processor_code in provider_configs:
        return GenericPaymentProcessor(processor_code, payment_method=payment_method)

    raise ValueError(f"Unsupported payment provider: {processor_code}")


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
        return get_configured_payment_processor(
            processor_code,
            payment_method=payment_method,
        )

    processor_code = getattr(
        settings,
        "BANK_TRANSFER_PAYMENT_PROCESSOR",
        ManualBankTransferProcessor.code,
    )
    return get_configured_payment_processor(
        processor_code,
        payment_method=payment_method,
    )


def get_payment_processor_by_provider(provider_name: str) -> BasePaymentProcessor:
    return get_configured_payment_processor(provider_name)


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
    processor = get_payment_processor_by_provider(instruction.provider_name)
    return processor.authorize_payment(
        instruction=instruction,
        cardholder_name=cardholder_name,
        card_number=card_number,
        expiry_month=expiry_month,
        expiry_year=expiry_year,
        cvv=cvv,
        billing_postal_code=billing_postal_code,
    )
