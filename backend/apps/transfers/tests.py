from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import SenderProfile
from apps.countries.models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    Country,
    CountryCorridor,
    Currency,
    PayoutProvider,
)
from apps.quotes.models import ExchangeRate, FeeRule, Quote
from apps.quotes.services import calculate_fee_amount, get_rate_for_corridor
from apps.recipients.models import Recipient, RecipientMobileMoneyAccount
from common.choices import PayoutMethod
from common.email_providers import send_transactional_email
from common.models import OperationalAuditLog

from .models import (
    RecipientVerificationRule,
    Transfer,
    TransferAmlRule,
    TransferComplianceEvent,
    TransferComplianceFlag,
    TransferLimitRule,
    TransferPaymentAction,
    TransferPaymentFraudRule,
    TransferPaymentInstruction,
    TransferPaymentWebhookEvent,
    TransferPayoutAttempt,
    TransferNotification,
    TransferRiskRule,
    TransferSanctionsCheck,
    TransferStatusEvent,
)
from .services import (
    apply_payment_instruction_status,
    auto_advance_transfer_after_funding,
    transition_transfer_status,
)


User = get_user_model()


class MockProviderResponse:
    def __init__(self, body="", status_code=200):
        self.body = body.encode("utf-8")
        self.status = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_BASE_URL="https://app.example.com",
)
class CoreTransferProductTests(APITestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar")
        self.zmw = Currency.objects.create(code="ZMW", name="Zambian Kwacha")
        self.us = Country.objects.create(
            name="United States",
            iso_code="US",
            dialing_code="+1",
            currency=self.usd,
            is_sender_enabled=True,
        )
        self.zambia = Country.objects.create(
            name="Zambia",
            iso_code="ZM",
            dialing_code="+260",
            currency=self.zmw,
            is_destination_enabled=True,
        )
        self.corridor = CountryCorridor.objects.create(
            source_country=self.us,
            destination_country=self.zambia,
            source_currency=self.usd,
            destination_currency=self.zmw,
            min_send_amount=Decimal("10.00"),
            max_send_amount=Decimal("5000.00"),
        )
        ExchangeRate.objects.create(
            corridor=self.corridor,
            rate=Decimal("25.50000000"),
            provider_name="test_rate",
            effective_at=timezone.now(),
        )
        FeeRule.objects.create(
            corridor=self.corridor,
            payout_method=PayoutMethod.MOBILE_MONEY,
            min_amount=Decimal("10.00"),
            max_amount=Decimal("5000.00"),
            fixed_fee=Decimal("2.99"),
            percentage_fee=Decimal("1.50"),
        )
        self.payout_provider, _ = PayoutProvider.objects.update_or_create(
            code="internal_mobile_money",
            defaults={
                "name": "Internal mobile money operations",
                "payout_method": PayoutMethod.MOBILE_MONEY,
                "is_active": True,
            },
        )
        self.payout_method_route = CorridorPayoutMethod.objects.create(
            corridor=self.corridor,
            payout_method=PayoutMethod.MOBILE_MONEY,
        )
        CorridorPayoutProvider.objects.create(
            corridor_payout_method=self.payout_method_route,
            provider=self.payout_provider,
            priority=10,
        )
        self.sender = User.objects.create_user(
            email="sender@example.com",
            password="test-password-123",
            first_name="Sam",
            last_name="Sender",
        )
        self.other_sender = User.objects.create_user(
            email="other@example.com",
            password="test-password-123",
        )
        self.staff = User.objects.create_user(
            email="ops@example.com",
            password="test-password-123",
            is_staff=True,
        )
        self.recipient = Recipient.objects.create(
            sender=self.sender,
            first_name="Mary",
            last_name="Banda",
            phone_number="+260971234567",
            country=self.zambia,
        )
        RecipientMobileMoneyAccount.objects.create(
            recipient=self.recipient,
            provider_name="MTN",
            mobile_number="+260971234567",
            account_name="Mary Banda",
            is_default=True,
        )

    def create_quote(self, *, sender=None, recipient=None, send_amount=Decimal("100.00")):
        return Quote.objects.create(
            sender=sender or self.sender,
            recipient=recipient or self.recipient,
            source_country=self.us,
            destination_country=self.zambia,
            source_currency=self.usd,
            destination_currency=self.zmw,
            payout_method=PayoutMethod.MOBILE_MONEY,
            send_amount=send_amount,
            fee_amount=Decimal("4.49"),
            exchange_rate=Decimal("25.50000000"),
            rate_source="database",
            rate_provider_name="test_rate",
            is_primary_rate=True,
            is_live_rate=False,
            receive_amount=(send_amount * Decimal("25.50000000")).quantize(
                Decimal("0.01"),
            ),
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    def create_transfer(
        self,
        *,
        status_value=Transfer.Status.AWAITING_FUNDING,
        send_amount=Decimal("100.00"),
    ):
        quote = self.create_quote(send_amount=send_amount)
        transfer = Transfer.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            quote=quote,
            source_country=self.us,
            destination_country=self.zambia,
            source_currency=self.usd,
            destination_currency=self.zmw,
            payout_method=PayoutMethod.MOBILE_MONEY,
            payout_provider=self.payout_provider,
            send_amount=quote.send_amount,
            fee_amount=quote.fee_amount,
            exchange_rate=quote.exchange_rate,
            rate_source=quote.rate_source,
            rate_provider_name=quote.rate_provider_name,
            is_primary_rate=quote.is_primary_rate,
            is_live_rate=quote.is_live_rate,
            receive_amount=quote.receive_amount,
            status=status_value,
        )
        if status_value != Transfer.Status.AWAITING_FUNDING:
            transfer.funding_status = Transfer.FundingStatus.RECEIVED
            transfer.save(update_fields=("funding_status", "updated_at"))
        return transfer

    def test_rate_and_fee_are_data_backed(self):
        rate_result = get_rate_for_corridor(self.corridor)
        fee_amount = calculate_fee_amount(
            self.corridor,
            PayoutMethod.MOBILE_MONEY,
            Decimal("100.00"),
        )

        self.assertEqual(rate_result.exchange_rate, Decimal("25.50000000"))
        self.assertEqual(fee_amount, Decimal("4.49"))

    def test_transfer_detail_is_scoped_to_owner(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.other_sender)

        response = self.client.get(
            reverse("transfer-detail", kwargs={"pk": transfer.pk}),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_customer_transfer_detail_hides_internal_provider_and_review_data(self):
        transfer = self.create_transfer(status_value=Transfer.Status.PROCESSING_PAYOUT)
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="internal_card_processor",
            amount=transfer.send_amount + transfer.fee_amount,
            currency=self.usd,
            status=TransferPaymentInstruction.Status.PAID,
            status_reason="Internal processor message.",
        )
        TransferPayoutAttempt.objects.create(
            transfer=transfer,
            provider=self.payout_provider,
            payout_method=PayoutMethod.MOBILE_MONEY,
            attempt_number=1,
            amount=transfer.receive_amount,
            currency=self.zmw,
            status=TransferPayoutAttempt.Status.SUBMITTED,
            request_payload={"secret": "do-not-expose"},
            response_payload={"provider_status": "do-not-expose"},
        )
        TransferStatusEvent.objects.create(
            transfer=transfer,
            from_status=Transfer.Status.UNDER_REVIEW,
            to_status=Transfer.Status.PROCESSING_PAYOUT,
            changed_by=self.staff,
            note="Internal operations note.",
        )
        self.client.force_authenticate(self.sender)

        response = self.client.get(
            reverse("transfer-detail", kwargs={"pk": transfer.pk}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("payout_provider", response.data)
        self.assertNotIn("payout_provider_details", response.data)
        self.assertNotIn("latest_payout_attempt", response.data)
        self.assertNotIn("note", response.data["status_events"][0])
        payment_instruction = response.data["latest_payment_instruction"]
        self.assertEqual(payment_instruction["id"], str(instruction.id))
        self.assertNotIn("provider_name", payment_instruction)
        self.assertNotIn("provider_reference", payment_instruction)
        serialized_response = json.dumps(response.data, default=str)
        self.assertNotIn("request_payload", serialized_response)
        self.assertNotIn("response_payload", serialized_response)
        self.assertNotIn("do-not-expose", serialized_response)
        self.assertNotIn("Internal operations note.", serialized_response)

    def test_payment_instruction_and_mock_funding_complete_transfer(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )
        self.assertEqual(instruction_response.status_code, status.HTTP_201_CREATED)
        instruction_id = instruction_response.data["id"]

        authorization_response = self.client.post(
            reverse(
                "transfer-payment-instruction-authorize",
                kwargs={"pk": transfer.pk, "instruction_id": instruction_id},
            ),
            {
                "cardholder_name": "Sam Sender",
                "card_number": "4242 4242 4242 4242",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "billing_postal_code": "80202",
            },
            format="json",
        )
        self.assertEqual(authorization_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            authorization_response.data["status"],
            TransferPaymentInstruction.Status.AUTHORIZED,
        )

        funding_response = self.client.post(
            reverse("transfer-funding", kwargs={"pk": transfer.pk}),
            {
                "payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
                "payment_instruction_id": instruction_id,
                "note": "Received in test.",
            },
            format="json",
        )

        self.assertEqual(funding_response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        instruction = TransferPaymentInstruction.objects.get(id=instruction_id)
        self.assertEqual(transfer.status, Transfer.Status.PROCESSING_PAYOUT)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.RECEIVED)
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.APPROVED)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.SUBMITTED)
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.PAID)
        self.assertTrue(
            transfer.status_events.filter(
                to_status=Transfer.Status.FUNDING_RECEIVED,
            ).exists(),
        )
        self.assertTrue(
            transfer.status_events.filter(
                to_status=Transfer.Status.APPROVED,
                note="Auto-approved after funding received for clear compliance transfer.",
            ).exists(),
        )
        self.assertTrue(
            transfer.status_events.filter(
                to_status=Transfer.Status.PROCESSING_PAYOUT,
            ).exists(),
        )
        payout_attempt = transfer.payout_attempts.get()
        self.assertEqual(payout_attempt.provider, self.payout_provider)
        self.assertEqual(payout_attempt.status, TransferPayoutAttempt.Status.SUBMITTED)
        notification_types = set(
            transfer.notifications.values_list("event_type", flat=True),
        )
        self.assertIn(
            TransferNotification.EventType.TRANSFER_IN_PROGRESS,
            notification_types,
        )
        self.assertIn(
            TransferNotification.EventType.PAYMENT_RECEIVED,
            notification_types,
        )
        self.assertIn(TransferNotification.EventType.RECEIPT, notification_types)
        self.assertTrue(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.PAYMENT_RECEIVED,
                subject=f"Payment received for transfer {transfer.reference}",
            ).exists(),
        )

    def test_auto_advance_after_funding_skips_when_transfer_is_not_low_risk(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        transfer.compliance_status = Transfer.ComplianceStatus.UNDER_REVIEW
        transfer.save(update_fields=("compliance_status", "updated_at"))

        auto_advance_transfer_after_funding(transfer)

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.FUNDING_RECEIVED)
        self.assertEqual(
            transfer.compliance_status,
            Transfer.ComplianceStatus.UNDER_REVIEW,
        )
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.NOT_STARTED)
        self.assertFalse(transfer.payout_attempts.exists())

    def test_card_payment_instruction_prepares_processor_ready_session(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.PENDING_AUTHORIZATION,
        )
        self.assertEqual(instruction.provider_name, "mock_card_processor")
        self.assertEqual(
            instruction.instructions["integration_mode"],
            "mock_embedded_card",
        )
        self.assertEqual(instruction.instructions["next_action"], "authorize_card")
        self.assertEqual(len(instruction.instructions["card_fields"]), 6)
        self.assertEqual(instruction.instructions["test_cards"][0]["outcome"], "authorized")

    @override_settings(
        CARD_PAYMENT_PROCESSOR="hosted_card_provider",
        PAYMENT_PROVIDER_CONFIGS={
            "hosted_card_provider": {
                "display_name": "Hosted card provider",
                "api_key": "secret-payment-key",
                "checkout_url": "https://checkout.example/pay",
            },
        },
    )
    def test_configured_card_processor_prepares_provider_handoff(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        self.assertEqual(instruction.provider_name, "hosted_card_provider")
        self.assertNotIn("provider_name", response.data)
        self.assertNotIn("provider_reference", response.data)
        instructions = response.data["instructions"]
        self.assertEqual(instructions["integration_mode"], "hosted_card_checkout")
        self.assertEqual(instructions["checkout_url"], "https://checkout.example/pay")
        self.assertTrue(instructions["requires_provider_webhook"])
        self.assertTrue(
            instructions["provider_config"]["api_key_configured"],
        )
        self.assertNotIn("secret-payment-key", str(instructions))

    def test_credit_card_payment_instruction_uses_card_processor(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.CREDIT_CARD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.PENDING_AUTHORIZATION,
        )
        self.assertEqual(instruction.provider_name, "mock_card_processor")
        self.assertEqual(
            instruction.instructions["integration_mode"],
            "mock_embedded_card",
        )

    def test_card_authorization_endpoint_marks_instruction_authorized(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )
        self.assertEqual(instruction_response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(
            reverse(
                "transfer-payment-instruction-authorize",
                kwargs={
                    "pk": transfer.pk,
                    "instruction_id": instruction_response.data["id"],
                },
            ),
            {
                "cardholder_name": "Sam Sender",
                "card_number": "4242 4242 4242 4242",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "billing_postal_code": "80202",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        transfer.refresh_from_db()
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.AUTHORIZED,
        )
        self.assertIsNotNone(instruction.authorized_at)
        self.assertEqual(
            instruction.instructions["authorization_masked_card"],
            "**** **** **** 4242",
        )
        self.assertEqual(transfer.status, Transfer.Status.AWAITING_FUNDING)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.PENDING)

    def test_card_authorization_decline_marks_instruction_failed(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )
        self.assertEqual(instruction_response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(
            reverse(
                "transfer-payment-instruction-authorize",
                kwargs={
                    "pk": transfer.pk,
                    "instruction_id": instruction_response.data["id"],
                },
            ),
            {
                "cardholder_name": "Sam Sender",
                "card_number": "4000 0000 0000 0002",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "billing_postal_code": "80202",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        transfer.refresh_from_db()
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.FAILED,
        )
        self.assertEqual(transfer.status, Transfer.Status.AWAITING_FUNDING)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.FAILED)
        self.assertEqual(
            instruction.status_reason,
            "Card issuer declined the authorization.",
        )

    def test_bank_transfer_instruction_remains_manual(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.BANK_TRANSFER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.NOT_STARTED,
        )
        self.assertEqual(instruction.provider_name, "manual_bank_transfer")
        self.assertEqual(
            instruction.instructions["integration_mode"],
            "manual_bank_transfer",
        )

    def test_card_funding_requires_authorized_instruction(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )
        self.assertEqual(instruction_response.status_code, status.HTTP_201_CREATED)

        funding_response = self.client.post(
            reverse("transfer-funding", kwargs={"pk": transfer.pk}),
            {
                "payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
                "payment_instruction_id": instruction_response.data["id"],
                "note": "Attempted before authorization.",
            },
            format="json",
        )

        self.assertEqual(funding_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "Card payment must be authorized before funding is confirmed.",
            str(funding_response.data),
        )

    def test_cardholder_name_mismatch_fraud_rule_holds_payment(self):
        TransferPaymentFraudRule.objects.create(
            name="Cardholder name mismatch",
            code="PAYMENT_NAME_MISMATCH",
            rule_type=TransferPaymentFraudRule.RuleType.CARDHOLDER_NAME_MISMATCH,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            action=TransferPaymentFraudRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)
        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )

        response = self.client.post(
            reverse(
                "transfer-payment-instruction-authorize",
                kwargs={
                    "pk": transfer.pk,
                    "instruction_id": instruction_response.data["id"],
                },
            ),
            {
                "cardholder_name": "Jordan Cardholder",
                "card_number": "4242 4242 4242 4242",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "billing_postal_code": "80202",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        transfer.refresh_from_db()
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.REQUIRES_REVIEW,
        )
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        flag = transfer.compliance_flags.get(code="PAYMENT_NAME_MISMATCH")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.PAYMENT)
        self.assertEqual(flag.metadata["cardholder_name"], "Jordan Cardholder")

    def test_unusual_payment_amount_fraud_rule_flags_authorized_payment(self):
        TransferPaymentFraudRule.objects.create(
            name="Unusual payment amount",
            code="PAYMENT_UNUSUAL_AMOUNT",
            rule_type=TransferPaymentFraudRule.RuleType.UNUSUAL_AMOUNT,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            threshold_amount=Decimal("100.00"),
            action=TransferPaymentFraudRule.Action.FLAG,
            severity=TransferComplianceFlag.Severity.MEDIUM,
        )
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)
        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )

        response = self.client.post(
            reverse(
                "transfer-payment-instruction-authorize",
                kwargs={
                    "pk": transfer.pk,
                    "instruction_id": instruction_response.data["id"],
                },
            ),
            {
                "cardholder_name": "Sam Sender",
                "card_number": "4242 4242 4242 4242",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "billing_postal_code": "80202",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction = TransferPaymentInstruction.objects.get(id=response.data["id"])
        transfer.refresh_from_db()
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.AUTHORIZED,
        )
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.FLAGGED)
        flag = transfer.compliance_flags.get(code="PAYMENT_UNUSUAL_AMOUNT")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.PAYMENT)
        self.assertEqual(flag.metadata["payment_amount"], "104.49")

    def test_repeated_failed_payment_attempts_can_hold_transfer(self):
        TransferPaymentFraudRule.objects.create(
            name="Repeated failed card attempts",
            code="PAYMENT_REPEATED_FAILURES",
            rule_type=TransferPaymentFraudRule.RuleType.REPEATED_ATTEMPTS,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            attempt_count=2,
            window_minutes=60,
            action=TransferPaymentFraudRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)

        for index in range(2):
            instruction_response = self.client.post(
                reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
                {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
                format="json",
            )
            self.client.post(
                reverse(
                    "transfer-payment-instruction-authorize",
                    kwargs={
                        "pk": transfer.pk,
                        "instruction_id": instruction_response.data["id"],
                    },
                ),
                {
                    "cardholder_name": "Sam Sender",
                    "card_number": "4000 0000 0000 0002",
                    "expiry_month": 12,
                    "expiry_year": 2030,
                    "cvv": "123",
                    "billing_postal_code": "80202",
                },
                format="json",
            )

        transfer.refresh_from_db()
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        flag = transfer.compliance_flags.get(code="PAYMENT_REPEATED_FAILURES")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.PAYMENT)
        self.assertEqual(flag.metadata["attempt_count"], "2")

    def test_payment_fraud_hold_blocks_funding_confirmation(self):
        TransferPaymentFraudRule.objects.create(
            name="Compliance-held payment block",
            code="PAYMENT_COMPLIANCE_HOLD",
            rule_type=TransferPaymentFraudRule.RuleType.COMPLIANCE_HOLD,
            payment_method=TransferPaymentInstruction.PaymentMethod.BANK_TRANSFER,
            action=TransferPaymentFraudRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        transfer = self.create_transfer()
        transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
        transfer.save(update_fields=("compliance_status", "updated_at"))
        self.client.force_authenticate(self.sender)
        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.BANK_TRANSFER},
            format="json",
        )

        response = self.client.post(
            reverse("transfer-funding", kwargs={"pk": transfer.pk}),
            {
                "payment_method": TransferPaymentInstruction.PaymentMethod.BANK_TRANSFER,
                "payment_instruction_id": instruction_response.data["id"],
                "note": "Attempted while compliance hold is open.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Payment requires fraud review", str(response.data))
        instruction = TransferPaymentInstruction.objects.get(
            id=instruction_response.data["id"],
        )
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.REQUIRES_REVIEW,
        )
        flag = transfer.compliance_flags.get(code="PAYMENT_COMPLIANCE_HOLD")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.PAYMENT)

    @override_settings(DEBUG=False, PAYMENT_WEBHOOK_SECRETS={})
    def test_payment_webhook_requires_configured_secret_in_production(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse(
                "transfer-payment-webhook",
                kwargs={"provider_name": "mock_card_processor"},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("not configured", str(response.data["detail"]))

    def test_payment_webhook_paid_event_marks_instruction_paid_and_logs_event(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)
        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )
        instruction = TransferPaymentInstruction.objects.get(id=instruction_response.data["id"])
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse(
                "transfer-payment-webhook",
                kwargs={"provider_name": instruction.provider_name},
            ),
            {
                "event_id": "evt_paid_1",
                "event_type": "payment.captured",
                "provider_reference": instruction.provider_reference,
                "payment_status": TransferPaymentInstruction.Status.PAID,
                "status_reason": "Captured by processor.",
                "amount": "104.49",
                "currency_code": "USD",
                "metadata": {"capture_reference": "cap_001"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["duplicate"])
        instruction.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.PAID)
        self.assertEqual(transfer.status, Transfer.Status.PROCESSING_PAYOUT)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.RECEIVED)
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.APPROVED)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.SUBMITTED)
        self.assertEqual(transfer.payout_attempts.count(), 1)
        event = TransferPaymentWebhookEvent.objects.get(provider_event_id="evt_paid_1")
        self.assertEqual(
            event.processing_status,
            TransferPaymentWebhookEvent.ProcessingStatus.PROCESSED,
        )
        self.assertEqual(event.resulting_payment_status, TransferPaymentInstruction.Status.PAID)

    def test_duplicate_payment_webhook_event_is_idempotent(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)
        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )
        instruction = TransferPaymentInstruction.objects.get(id=instruction_response.data["id"])
        self.client.force_authenticate(user=None)

        payload = {
            "event_id": "evt_paid_duplicate",
            "event_type": "payment.captured",
            "provider_reference": instruction.provider_reference,
            "payment_status": TransferPaymentInstruction.Status.PAID,
            "status_reason": "Captured once.",
            "amount": "104.49",
            "currency_code": "USD",
        }
        first_response = self.client.post(
            reverse(
                "transfer-payment-webhook",
                kwargs={"provider_name": instruction.provider_name},
            ),
            payload,
            format="json",
        )
        second_response = self.client.post(
            reverse(
                "transfer-payment-webhook",
                kwargs={"provider_name": instruction.provider_name},
            ),
            payload,
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertFalse(first_response.data["duplicate"])
        self.assertTrue(second_response.data["duplicate"])
        self.assertEqual(
            TransferPaymentWebhookEvent.objects.filter(
                provider_name=instruction.provider_name,
                provider_event_id="evt_paid_duplicate",
            ).count(),
            1,
        )
        transfer.refresh_from_db()
        self.assertEqual(
            transfer.status_events.filter(
                to_status=Transfer.Status.FUNDING_RECEIVED,
            ).count(),
            1,
        )

    def test_payment_webhook_failed_event_marks_instruction_failed(self):
        transfer = self.create_transfer()
        self.client.force_authenticate(self.sender)
        instruction_response = self.client.post(
            reverse("transfer-payment-instructions", kwargs={"pk": transfer.pk}),
            {"payment_method": TransferPaymentInstruction.PaymentMethod.DEBIT_CARD},
            format="json",
        )
        instruction = TransferPaymentInstruction.objects.get(id=instruction_response.data["id"])
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse(
                "transfer-payment-webhook",
                kwargs={"provider_name": instruction.provider_name},
            ),
            {
                "event_id": "evt_failed_1",
                "event_type": "payment.failed",
                "provider_reference": instruction.provider_reference,
                "payment_status": TransferPaymentInstruction.Status.FAILED,
                "status_reason": "Processor marked the payment as failed.",
                "amount": "104.49",
                "currency_code": "USD",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.FAILED)
        self.assertEqual(transfer.status, Transfer.Status.AWAITING_FUNDING)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.FAILED)

    def test_payment_webhook_refund_event_moves_transfer_to_refunded(self):
        transfer = self.create_transfer()
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="mock_card_processor",
            amount=Decimal("104.49"),
            currency=self.usd,
        )
        apply_payment_instruction_status(
            instruction,
            TransferPaymentInstruction.Status.PAID,
            changed_by=self.sender,
            note="Payment settled.",
        )

        response = self.client.post(
            reverse(
                "transfer-payment-webhook",
                kwargs={"provider_name": instruction.provider_name},
            ),
            {
                "event_id": "evt_refund_1",
                "event_type": "charge.refunded",
                "provider_reference": instruction.provider_reference,
                "payment_status": TransferPaymentInstruction.Status.REFUNDED,
                "status_reason": "Customer refunded after settlement.",
                "amount": "104.49",
                "currency_code": "USD",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.REFUNDED)
        self.assertEqual(transfer.status, Transfer.Status.REFUNDED)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.REFUNDED)

    def test_staff_can_refund_paid_payment_instruction(self):
        transfer = self.create_transfer()
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="mock_card_processor",
            amount=Decimal("104.49"),
            currency=self.usd,
        )
        apply_payment_instruction_status(
            instruction,
            TransferPaymentInstruction.Status.PAID,
            changed_by=self.sender,
            note="Payment captured.",
        )
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("transfer-payment-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferPaymentAction.Action.REFUND,
                "payment_instruction_id": str(instruction.id),
                "reason_code": "customer_request",
                "note": "Customer requested refund before payout.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.REFUNDED)
        self.assertEqual(transfer.status, Transfer.Status.REFUNDED)
        action = TransferPaymentAction.objects.get(payment_instruction=instruction)
        self.assertEqual(action.status, TransferPaymentAction.Status.COMPLETED)
        self.assertEqual(action.provider_action_reference[:4], "RFD-")
        self.assertEqual(action.requested_by, self.staff)

    def test_staff_can_reverse_authorized_payment_instruction(self):
        transfer = self.create_transfer()
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="mock_card_processor",
            amount=Decimal("104.49"),
            currency=self.usd,
        )
        apply_payment_instruction_status(
            instruction,
            TransferPaymentInstruction.Status.AUTHORIZED,
            changed_by=self.sender,
            note="Payment authorized.",
        )
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("transfer-payment-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferPaymentAction.Action.REVERSAL,
                "payment_instruction_id": str(instruction.id),
                "reason_code": "risk_hold",
                "note": "Authorization reversed after risk review.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        instruction.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.REVERSED)
        self.assertEqual(transfer.status, Transfer.Status.REFUNDED)
        action = TransferPaymentAction.objects.get(payment_instruction=instruction)
        self.assertEqual(action.status, TransferPaymentAction.Status.COMPLETED)
        self.assertEqual(action.provider_action_reference[:4], "REV-")

    def test_payment_action_rejects_invalid_refund_state(self):
        transfer = self.create_transfer()
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="mock_card_processor",
            amount=Decimal("104.49"),
            currency=self.usd,
            status=TransferPaymentInstruction.Status.AUTHORIZED,
        )
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("transfer-payment-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferPaymentAction.Action.REFUND,
                "payment_instruction_id": str(instruction.id),
                "note": "Trying invalid refund.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only paid payment instructions can be refunded", str(response.data))

    def test_payment_action_requires_staff(self):
        transfer = self.create_transfer()
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="mock_card_processor",
            amount=Decimal("104.49"),
            currency=self.usd,
            status=TransferPaymentInstruction.Status.PAID,
        )
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-payment-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferPaymentAction.Action.REFUND,
                "payment_instruction_id": str(instruction.id),
                "note": "Customer cannot self-refund.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authorized_payment_keeps_transfer_awaiting_funding(self):
        transfer = self.create_transfer()
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="mock_card_processor",
            amount=Decimal("104.49"),
            currency=self.usd,
        )

        updated_transfer = apply_payment_instruction_status(
            instruction,
            TransferPaymentInstruction.Status.AUTHORIZED,
            changed_by=self.sender,
            note="Payment authorized in gateway.",
        )

        instruction.refresh_from_db()
        updated_transfer.refresh_from_db()
        self.assertEqual(
            instruction.status,
            TransferPaymentInstruction.Status.AUTHORIZED,
        )
        self.assertIsNotNone(instruction.authorized_at)
        self.assertEqual(updated_transfer.status, Transfer.Status.AWAITING_FUNDING)
        self.assertEqual(updated_transfer.funding_status, Transfer.FundingStatus.PENDING)

    def test_failed_payment_marks_transfer_funding_failed(self):
        transfer = self.create_transfer()
        instruction = TransferPaymentInstruction.objects.create(
            transfer=transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            provider_name="mock_card_processor",
            amount=Decimal("104.49"),
            currency=self.usd,
        )

        updated_transfer = apply_payment_instruction_status(
            instruction,
            TransferPaymentInstruction.Status.FAILED,
            changed_by=self.sender,
            status_reason="Card issuer declined the authorization.",
        )

        instruction.refresh_from_db()
        updated_transfer.refresh_from_db()
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.FAILED)
        self.assertEqual(
            updated_transfer.funding_status,
            Transfer.FundingStatus.FAILED,
        )
        self.assertEqual(updated_transfer.status, Transfer.Status.AWAITING_FUNDING)
        self.assertTrue(
            updated_transfer.notifications.filter(
                event_type=TransferNotification.EventType.TRANSACTION_FAILED,
                trigger_id=str(instruction.id),
            ).exists(),
        )

    def test_staff_can_advance_status_through_payout_lifecycle(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)

        transitions = (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
            Transfer.Status.PAID_OUT,
            Transfer.Status.COMPLETED,
        )

        for target_status in transitions:
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            transfer.refresh_from_db()
            self.assertEqual(transfer.status, target_status)

        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.APPROVED)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.PAID_OUT)
        payout_attempt = transfer.payout_attempts.get()
        self.assertEqual(payout_attempt.provider, self.payout_provider)
        self.assertEqual(payout_attempt.status, TransferPayoutAttempt.Status.PAID_OUT)
        self.assertEqual(
            transfer.status_events.filter(to_status=Transfer.Status.COMPLETED).count(),
            1,
        )
        audit_log = OperationalAuditLog.objects.get(
            action_name="transfer.status_transition",
            target_id=str(transfer.id),
            new_status=Transfer.Status.COMPLETED,
        )
        self.assertEqual(audit_log.actor, self.staff)
        self.assertEqual(audit_log.target_reference, transfer.reference)
        self.assertEqual(audit_log.previous_status, Transfer.Status.PAID_OUT)
        self.assertEqual(audit_log.note, "Move to completed.")
        self.assertTrue(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.PAYOUT_COMPLETE,
            ).exists(),
        )
        self.assertTrue(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.TRANSFER_COMPLETED,
            ).exists(),
        )

    @override_settings(
        PAYOUT_PROVIDER_CONFIGS={
            "mobile_money_provider": {
                "display_name": "Mobile money provider",
                "api_key": "secret-payout-key",
            },
        },
    )
    def test_configured_payout_provider_receives_external_handoff(self):
        payout_provider = PayoutProvider.objects.create(
            code="mobile_money_provider",
            name="Mobile money provider",
            payout_method=PayoutMethod.MOBILE_MONEY,
            metadata={"processor": "external"},
        )
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        transfer.payout_provider = payout_provider
        transfer.save(update_fields=("payout_provider", "updated_at"))
        self.client.force_authenticate(self.staff)

        for target_status in (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
        ):
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        attempt = transfer.payout_attempts.get()
        self.assertEqual(attempt.provider, payout_provider)
        self.assertEqual(
            attempt.request_payload["integration_mode"],
            "external_payout_provider",
        )
        self.assertTrue(
            attempt.request_payload["provider_config"]["api_key_configured"],
        )
        self.assertNotIn("secret-payout-key", str(attempt.request_payload))

    @override_settings(
        PAYOUT_PROVIDER_CONFIGS={
            "mtn_momo": {
                "display_name": "MTN MoMo",
                "base_url": "https://sandbox.momodeveloper.mtn.com",
                "api_key": "secret-subscription-key",
                "user_id": "mtn-api-user",
                "api_secret": "mtn-api-secret",
                "target_environment": "sandbox",
                "currency": "EUR",
            },
        },
    )
    @patch("apps.transfers.payout_providers.urlopen")
    def test_mtn_momo_payout_submission_maps_transfer_request(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            MockProviderResponse('{"access_token":"mtn-access-token"}'),
            MockProviderResponse(""),
        ]
        payout_provider = PayoutProvider.objects.create(
            code="mtn_momo",
            name="MTN MoMo",
            payout_method=PayoutMethod.MOBILE_MONEY,
            metadata={"processor": "mtn_momo"},
        )
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        transfer.payout_provider = payout_provider
        transfer.save(update_fields=("payout_provider", "updated_at"))
        self.client.force_authenticate(self.staff)

        for target_status in (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
        ):
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        transfer.refresh_from_db()
        attempt = transfer.payout_attempts.get()
        transfer_request = mocked_urlopen.call_args_list[1].args[0]
        payload = json.loads(transfer_request.data.decode("utf-8"))
        self.assertEqual(attempt.provider, payout_provider)
        self.assertEqual(attempt.status, TransferPayoutAttempt.Status.PROCESSING)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.PROCESSING)
        self.assertEqual(payload["amount"], str(attempt.amount))
        self.assertEqual(payload["currency"], "EUR")
        self.assertEqual(payload["externalId"], transfer.reference)
        self.assertEqual(payload["payee"]["partyIdType"], "MSISDN")
        self.assertEqual(payload["payee"]["partyId"], "260971234567")
        self.assertEqual(
            transfer_request.headers["X-reference-id"],
            attempt.provider_reference,
        )
        self.assertEqual(
            transfer_request.headers["Ocp-apim-subscription-key"],
            "secret-subscription-key",
        )
        self.assertNotIn("secret-subscription-key", str(attempt.request_payload))
        self.assertNotIn("mtn-api-secret", str(attempt.request_payload))

    @override_settings(
        PAYOUT_PROVIDER_CONFIGS={
            "mtn_momo": {
                "display_name": "MTN MoMo",
                "base_url": "https://sandbox.momodeveloper.mtn.com",
                "api_key": "secret-subscription-key",
                "user_id": "mtn-api-user",
                "api_secret": "mtn-api-secret",
                "target_environment": "sandbox",
                "currency": "EUR",
            },
        },
    )
    @patch("apps.transfers.payout_providers.urlopen")
    def test_mtn_momo_payout_timeout_marks_attempt_failed(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            MockProviderResponse('{"access_token":"mtn-access-token"}'),
            TimeoutError("timed out"),
        ]
        payout_provider = PayoutProvider.objects.create(
            code="mtn_momo",
            name="MTN MoMo",
            payout_method=PayoutMethod.MOBILE_MONEY,
            metadata={"processor": "mtn_momo"},
        )
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        transfer.payout_provider = payout_provider
        transfer.save(update_fields=("payout_provider", "updated_at"))
        self.client.force_authenticate(self.staff)

        for target_status in (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
        ):
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        transfer.refresh_from_db()
        attempt = transfer.payout_attempts.get()
        self.assertEqual(attempt.status, TransferPayoutAttempt.Status.FAILED)
        self.assertEqual(transfer.status, Transfer.Status.FAILED)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.FAILED)
        self.assertIn("timed out", attempt.status_reason)
        self.assertEqual(attempt.response_payload["provider_status"], "submission_failed")

    @override_settings(
        PAYOUT_PROVIDER_CONFIGS={
            "mtn_momo": {
                "display_name": "MTN MoMo",
                "base_url": "https://sandbox.momodeveloper.mtn.com",
                "api_key": "secret-subscription-key",
                "user_id": "mtn-api-user",
                "api_secret": "mtn-api-secret",
                "target_environment": "sandbox",
            },
        },
    )
    @patch("apps.transfers.payout_providers.urlopen")
    def test_mtn_momo_provider_status_sync_marks_payout_success(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            MockProviderResponse('{"access_token":"mtn-access-token"}'),
            MockProviderResponse(""),
            MockProviderResponse('{"access_token":"mtn-access-token"}'),
            MockProviderResponse(
                '{"status":"SUCCESSFUL","financialTransactionId":"mtn-ft-123"}',
            ),
        ]
        payout_provider = PayoutProvider.objects.create(
            code="mtn_momo",
            name="MTN MoMo",
            payout_method=PayoutMethod.MOBILE_MONEY,
            metadata={"processor": "mtn_momo"},
        )
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        transfer.payout_provider = payout_provider
        transfer.save(update_fields=("payout_provider", "updated_at"))
        self.client.force_authenticate(self.staff)
        for target_status in (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
        ):
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        attempt = transfer.payout_attempts.get()
        response = self.client.post(
            reverse(
                "transfer-payout-attempt-provider-sync",
                kwargs={"pk": transfer.pk, "attempt_id": attempt.id},
            ),
            {"note": "Poll MTN for latest payout status."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.PAID_OUT)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.PAID_OUT)
        self.assertEqual(attempt.status, TransferPayoutAttempt.Status.PAID_OUT)
        self.assertEqual(attempt.provider_status, "SUCCESSFUL")
        self.assertEqual(
            attempt.response_payload["provider_transaction_id"],
            "mtn-ft-123",
        )

    def test_payout_failure_can_be_retried_with_new_attempt(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)
        for target_status in (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
        ):
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        transfer.refresh_from_db()
        first_attempt = transfer.payout_attempts.get()
        failure_response = self.client.post(
            reverse(
                "transfer-payout-attempt-sync",
                kwargs={"pk": transfer.pk, "attempt_id": first_attempt.id},
            ),
            {
                "payout_status": TransferPayoutAttempt.Status.FAILED,
                "provider_event_id": "payout-failed-1",
                "provider_status": "failed",
                "status_reason": "Wallet provider rejected the payout.",
            },
            format="json",
        )
        self.assertEqual(failure_response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        first_attempt.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.FAILED)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.FAILED)
        self.assertEqual(first_attempt.status, TransferPayoutAttempt.Status.FAILED)
        self.assertTrue(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.TRANSACTION_FAILED,
            ).exists(),
        )

        retry_response = self.client.post(
            reverse(
                "transfer-payout-attempt-retry",
                kwargs={"pk": transfer.pk, "attempt_id": first_attempt.id},
            ),
            {"note": "Retry after wallet provider recovery."},
            format="json",
        )

        self.assertEqual(retry_response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        retry_attempt = transfer.payout_attempts.order_by("-attempt_number").first()
        self.assertEqual(transfer.status, Transfer.Status.PROCESSING_PAYOUT)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.SUBMITTED)
        self.assertEqual(retry_attempt.retry_of, first_attempt)
        self.assertEqual(retry_attempt.status, TransferPayoutAttempt.Status.SUBMITTED)

    def test_payout_webhook_sync_is_idempotent(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)
        for target_status in (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
        ):
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        transfer.refresh_from_db()
        attempt = transfer.payout_attempts.get()
        self.client.force_authenticate(user=None)

        payload = {
            "event_id": "payout-paid-1",
            "provider_reference": attempt.provider_reference,
            "payout_status": TransferPayoutAttempt.Status.PAID_OUT,
            "provider_status": "paid_out",
            "status_reason": "Provider confirmed payout.",
        }
        first_response = self.client.post(
            reverse(
                "transfer-payout-webhook",
                kwargs={"provider_code": self.payout_provider.code},
            ),
            payload,
            format="json",
        )
        duplicate_response = self.client.post(
            reverse(
                "transfer-payout-webhook",
                kwargs={"provider_code": self.payout_provider.code},
            ),
            payload,
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate_response.status_code, status.HTTP_200_OK)
        self.assertFalse(first_response.data["duplicate"])
        self.assertTrue(duplicate_response.data["duplicate"])
        transfer.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.PAID_OUT)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.PAID_OUT)
        self.assertEqual(
            attempt.events.filter(provider_event_id="payout-paid-1").count(),
            1,
        )
        self.assertEqual(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.PAYOUT_COMPLETE,
            ).count(),
            1,
        )

    @override_settings(DEBUG=False, PAYOUT_WEBHOOK_SECRETS={})
    def test_payout_webhook_requires_configured_secret_in_production(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse(
                "transfer-payout-webhook",
                kwargs={"provider_code": self.payout_provider.code},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("not configured", str(response.data["detail"]))

    def test_paid_out_payout_can_be_reversed(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)
        for target_status in (
            Transfer.Status.UNDER_REVIEW,
            Transfer.Status.APPROVED,
            Transfer.Status.PROCESSING_PAYOUT,
            Transfer.Status.PAID_OUT,
        ):
            response = self.client.post(
                reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
                {"status": target_status, "note": f"Move to {target_status}."},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        transfer.refresh_from_db()
        attempt = transfer.payout_attempts.get()
        response = self.client.post(
            reverse(
                "transfer-payout-attempt-reverse",
                kwargs={"pk": transfer.pk, "attempt_id": attempt.id},
            ),
            {"note": "Provider reversed the payout after settlement failure."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.FAILED)
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.REVERSED)
        self.assertEqual(attempt.status, TransferPayoutAttempt.Status.REVERSED)

    def test_status_transition_rejects_non_staff_and_invalid_moves(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)

        self.client.force_authenticate(self.sender)
        non_staff_response = self.client.post(
            reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
            {"status": Transfer.Status.UNDER_REVIEW},
            format="json",
        )
        self.assertEqual(non_staff_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.staff)
        invalid_response = self.client.post(
            reverse("transfer-status-transition", kwargs={"pk": transfer.pk}),
            {"status": Transfer.Status.COMPLETED},
            format="json",
        )
        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_operations_queue_lists_transfers_with_next_actions(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)

        response = self.client.get(
            reverse("transfer-operations-list"),
            {"status": Transfer.Status.FUNDING_RECEIVED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(transfer.id))
        self.assertEqual(response.data[0]["sender_email"], self.sender.email)
        self.assertIn(
            Transfer.Status.UNDER_REVIEW,
            {
                option["status"]
                for option in response.data[0]["allowed_next_statuses"]
            },
        )

        self.client.force_authenticate(self.sender)
        forbidden_response = self.client.get(reverse("transfer-operations-list"))
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_operations_queue_includes_compliance_flags(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        transfer.compliance_status = Transfer.ComplianceStatus.FLAGGED
        transfer.save(update_fields=("compliance_status", "updated_at"))
        TransferComplianceFlag.objects.create(
            transfer=transfer,
            category=TransferComplianceFlag.Category.RISK_RULE,
            severity=TransferComplianceFlag.Severity.HIGH,
            code="HIGH_AMOUNT",
            title="High amount review",
            description="Transfer amount requires staff review.",
            created_by=self.staff,
        )
        self.client.force_authenticate(self.staff)

        response = self.client.get(
            reverse("transfer-operations-list"),
            {"compliance_status": Transfer.ComplianceStatus.FLAGGED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["compliance_status"], "flagged")
        self.assertEqual(len(response.data[0]["compliance_flags"]), 1)
        self.assertEqual(
            response.data[0]["compliance_flags"][0]["code"],
            "HIGH_AMOUNT",
        )

    def test_staff_operations_reports_include_analytics(self):
        active_transfer = self.create_transfer(
            status_value=Transfer.Status.FUNDING_RECEIVED,
        )
        completed_transfer = self.create_transfer(
            status_value=Transfer.Status.COMPLETED,
        )
        TransferPaymentInstruction.objects.create(
            transfer=active_transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            amount=active_transfer.send_amount + active_transfer.fee_amount,
            currency=self.usd,
            status=TransferPaymentInstruction.Status.PAID,
        )
        TransferPaymentInstruction.objects.create(
            transfer=completed_transfer,
            payment_method=TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            amount=completed_transfer.send_amount + completed_transfer.fee_amount,
            currency=self.usd,
            status=TransferPaymentInstruction.Status.FAILED,
        )
        TransferPayoutAttempt.objects.create(
            transfer=active_transfer,
            provider=self.payout_provider,
            payout_method=PayoutMethod.MOBILE_MONEY,
            attempt_number=1,
            amount=active_transfer.receive_amount,
            currency=self.zmw,
            status=TransferPayoutAttempt.Status.FAILED,
        )
        SenderProfile.objects.create(
            user=self.sender,
            phone_number="+12025550123",
            country=self.us,
            kyc_status=SenderProfile.KycStatus.VERIFIED,
            kyc_submitted_at=timezone.now(),
            kyc_reviewed_at=timezone.now(),
        )
        pending_user = User.objects.create_user(
            email="pending-kyc@example.com",
            password="test-password-123",
        )
        SenderProfile.objects.create(
            user=pending_user,
            phone_number="+12025550124",
            country=self.us,
            kyc_status=SenderProfile.KycStatus.PENDING,
            kyc_submitted_at=timezone.now(),
        )
        self.client.force_authenticate(self.staff)

        response = self.client.get(reverse("transfer-operations-reports"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["transaction_volume"]["created_count"], 2)
        self.assertEqual(response.data["transaction_volume"]["completed_count"], 1)
        self.assertEqual(response.data["revenue"]["total_fee_amount"], "8.98")
        self.assertEqual(
            response.data["failed_payment_rates"]["failed_rate_percent"],
            "50.00",
        )
        self.assertEqual(
            response.data["failed_payout_rates"]["failed_rate_percent"],
            "100.00",
        )
        self.assertEqual(
            response.data["kyc_completion"]["completion_rate_percent"],
            "50.00",
        )
        self.assertEqual(response.data["funnel"][0]["value"], "quotes_created")
        self.assertIn("active_transfer_count", response.data["admin_reports"])

        self.client.force_authenticate(self.sender)
        forbidden_response = self.client.get(reverse("transfer-operations-reports"))
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_operations_report_rejects_invalid_date_range(self):
        self.client.force_authenticate(self.staff)

        response = self.client.get(
            reverse("transfer-operations-reports"),
            {"start_date": "2026-02-02", "end_date": "2026-02-01"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_can_export_transfer_records_csv(self):
        transfer = self.create_transfer(status_value=Transfer.Status.COMPLETED)
        self.client.force_authenticate(self.staff)

        response = self.client.get(reverse("transfer-operations-export-transfers"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])

        csv_text = response.content.decode()
        header = csv_text.splitlines()[0]
        self.assertIn("transfer_reference", header)
        self.assertIn("sender_email", header)
        self.assertIn("recipient_name", header)
        self.assertIn("send_amount", header)
        self.assertIn("receive_amount", header)
        self.assertIn("fee_amount", header)
        self.assertNotIn("provider_reference", header)
        self.assertNotIn("request_payload", header)
        self.assertNotIn("response_payload", header)
        self.assertNotIn("card", header.lower())
        self.assertIn(transfer.reference, csv_text)
        self.assertIn(self.sender.email, csv_text)
        self.assertIn("Mary Banda", csv_text)

    def test_staff_can_export_compliance_records_csv(self):
        transfer = self.create_transfer(status_value=Transfer.Status.UNDER_REVIEW)
        TransferComplianceEvent.objects.create(
            transfer=transfer,
            action=TransferComplianceEvent.Action.NOTE,
            from_compliance_status=Transfer.ComplianceStatus.FLAGGED,
            to_compliance_status=Transfer.ComplianceStatus.UNDER_REVIEW,
            from_transfer_status=Transfer.Status.FUNDING_RECEIVED,
            to_transfer_status=Transfer.Status.UNDER_REVIEW,
            note="Customer supplied clarification.",
            performed_by=self.staff,
            metadata={"internal_score": "do-not-export"},
        )
        self.client.force_authenticate(self.staff)

        response = self.client.get(reverse("transfer-operations-export-compliance"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", response["Content-Type"])

        csv_text = response.content.decode()
        header = csv_text.splitlines()[0]
        self.assertIn("transfer_reference", header)
        self.assertIn("action", header)
        self.assertIn("from_compliance_status", header)
        self.assertIn("to_compliance_status", header)
        self.assertIn("performed_by_email", header)
        self.assertNotIn("metadata", header)
        self.assertNotIn("screening_payload", header)
        self.assertNotIn("response_payload", header)
        self.assertIn(transfer.reference, csv_text)
        self.assertIn("Customer supplied clarification.", csv_text)
        self.assertNotIn("do-not-export", csv_text)

    def test_staff_can_export_operational_audit_logs_csv(self):
        audit_log = OperationalAuditLog.objects.create(
            actor=self.staff,
            action_name="transfer.status_transition",
            target_type="transfer",
            target_id="internal-target-id",
            target_reference="TRFEXPORT123",
            previous_status=Transfer.Status.UNDER_REVIEW,
            new_status=Transfer.Status.APPROVED,
            note="Reviewed by operations.",
            request_ip="203.0.113.10",
            user_agent="UnitTest/1.0",
            metadata={"provider_payload": "do-not-export"},
        )
        self.client.force_authenticate(self.staff)

        response = self.client.get(reverse("transfer-operations-export-audit"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", response["Content-Type"])

        csv_text = response.content.decode()
        header = csv_text.splitlines()[0]
        self.assertIn("audit_id", header)
        self.assertIn("actor_email", header)
        self.assertIn("action", header)
        self.assertIn("target_reference", header)
        self.assertIn("previous_status", header)
        self.assertIn("new_status", header)
        self.assertIn("request_ip", header)
        self.assertNotIn("metadata", header)
        self.assertNotIn("provider_payload", csv_text)
        self.assertIn(str(audit_log.id), csv_text)
        self.assertIn("TRFEXPORT123", csv_text)

    def test_operation_exports_require_staff_access(self):
        self.client.force_authenticate(self.sender)

        for route_name in (
            "transfer-operations-export-transfers",
            "transfer-operations-export-compliance",
            "transfer-operations-export-audit",
        ):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_transfer_creation_selects_payout_provider_from_corridor_route(self):
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.payout_provider, self.payout_provider)
        self.assertNotIn("payout_provider", response.data)
        self.assertNotIn("payout_provider_details", response.data)
        self.assertTrue(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.TRANSFER_INITIATED,
                recipient_email=self.sender.email,
            ).exists(),
        )
        self.assertTrue(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.TRANSFER_INITIATED,
                subject=(
                    "Your MbongoPay transfer has been initiated: "
                    f"{transfer.reference}"
                ),
            ).exists(),
        )

    def test_status_notifications_use_customer_safe_language(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)

        transition_transfer_status(
            transfer,
            Transfer.Status.UNDER_REVIEW,
            changed_by=self.staff,
            note="Internal compliance review note that should stay private.",
        )
        transfer.refresh_from_db()
        transition_transfer_status(
            transfer,
            Transfer.Status.APPROVED,
            changed_by=self.staff,
            note="Approved internally.",
        )
        transfer.refresh_from_db()
        transition_transfer_status(
            transfer,
            Transfer.Status.PROCESSING_PAYOUT,
            changed_by=self.staff,
            note="Submit payout.",
        )

        notification = transfer.notifications.get(
            event_type=TransferNotification.EventType.TRANSFER_IN_PROGRESS,
        )
        forbidden_terms = (
            "funding_received",
            "approved",
            "processing_payout",
            "MTN PENDING",
            "compliance",
            "Internal compliance review note",
        )
        for term in forbidden_terms:
            self.assertNotIn(term, notification.subject)
            self.assertNotIn(term, notification.body)
        self.assertEqual(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.TRANSFER_IN_PROGRESS,
            ).count(),
            1,
        )

    @override_settings(
        EMAIL_SERVICE_PROVIDER="resend",
        RESEND_API_KEY="resend-test-key",
        DEFAULT_FROM_EMAIL="MbongoPay <support@example.com>",
    )
    @patch("common.email_providers.request_json")
    def test_resend_provider_sends_transactional_email(self, mock_request_json):
        mock_request_json.return_value = {"id": "email_123"}

        result = send_transactional_email(
            subject="Transfer update",
            body="Your transfer is in progress.",
            recipient_emails=["sender@example.com"],
        )

        self.assertEqual(result.provider_name, "resend")
        self.assertEqual(result.provider_reference, "email_123")
        mock_request_json.assert_called_once()
        payload = mock_request_json.call_args.kwargs["payload"]
        self.assertEqual(payload["from"], "MbongoPay <support@example.com>")
        self.assertEqual(payload["to"], ["sender@example.com"])
        self.assertEqual(payload["subject"], "Transfer update")
        self.assertEqual(payload["text"], "Your transfer is in progress.")

    @override_settings(EMAIL_SERVICE_PROVIDER="resend", RESEND_API_KEY="")
    def test_email_delivery_failure_does_not_break_status_flow(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)

        with self.captureOnCommitCallbacks(execute=True):
            transition_transfer_status(
                transfer,
                Transfer.Status.UNDER_REVIEW,
                changed_by=self.staff,
                note="Move forward.",
            )

        transfer.refresh_from_db()
        notification = transfer.notifications.get(
            event_type=TransferNotification.EventType.TRANSFER_IN_PROGRESS,
        )
        self.assertEqual(transfer.status, Transfer.Status.UNDER_REVIEW)
        self.assertEqual(notification.status, TransferNotification.Status.FAILED)
        self.assertIn("email delivery failed", notification.error)
        self.assertNotIn("resend-test-key", notification.error)

    def test_transfer_creation_copies_quote_fx_metadata(self):
        quote = self.create_quote(send_amount=Decimal("100.00"))
        quote.rate_source = "open_exchange_rates"
        quote.rate_provider_name = "open_exchange_rates"
        quote.is_primary_rate = True
        quote.is_live_rate = True
        quote.save(
            update_fields=(
                "rate_source",
                "rate_provider_name",
                "is_primary_rate",
                "is_live_rate",
                "updated_at",
            ),
        )
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.rate_source, "open_exchange_rates")
        self.assertEqual(transfer.rate_provider_name, "open_exchange_rates")
        self.assertTrue(transfer.is_primary_rate)
        self.assertTrue(transfer.is_live_rate)
        self.assertEqual(response.data["rate_source"], "open_exchange_rates")
        self.assertEqual(response.data["rate_provider_name"], "open_exchange_rates")
        self.assertTrue(response.data["is_primary_rate"])
        self.assertTrue(response.data["is_live_rate"])

    def test_transfer_limit_rule_can_hold_transfer_on_creation(self):
        TransferLimitRule.objects.create(
            name="Single transfer hold threshold",
            code="SINGLE_TRANSFER_LIMIT",
            corridor=self.corridor,
            period=TransferLimitRule.Period.PER_TRANSFER,
            max_send_amount=Decimal("50.00"),
            action=TransferLimitRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        flag = transfer.compliance_flags.get(code="SINGLE_TRANSFER_LIMIT")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.LIMIT)
        self.assertEqual(flag.severity, TransferComplianceFlag.Severity.HIGH)
        self.assertEqual(flag.metadata["observed_amount"], "100.00")

    def test_daily_transfer_limit_uses_sender_activity(self):
        self.create_transfer(send_amount=Decimal("60.00"))
        TransferLimitRule.objects.create(
            name="Daily sender threshold",
            code="DAILY_SENDER_LIMIT",
            source_currency=self.usd,
            period=TransferLimitRule.Period.DAILY,
            max_send_amount=Decimal("100.00"),
            action=TransferLimitRule.Action.FLAG,
            severity=TransferComplianceFlag.Severity.MEDIUM,
        )
        quote = self.create_quote(send_amount=Decimal("50.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Bills",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.FLAGGED)
        flag = transfer.compliance_flags.get(code="DAILY_SENDER_LIMIT")
        self.assertEqual(flag.metadata["observed_amount"], "110.00")

    def test_high_amount_risk_rule_flags_transfer_on_creation(self):
        TransferRiskRule.objects.create(
            name="High amount review",
            code="HIGH_AMOUNT_REVIEW",
            corridor=self.corridor,
            rule_type=TransferRiskRule.RuleType.HIGH_AMOUNT,
            threshold_amount=Decimal("75.00"),
            action=TransferRiskRule.Action.FLAG,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "School fees",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.FLAGGED)
        flag = transfer.compliance_flags.get(code="HIGH_AMOUNT_REVIEW")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.RISK_RULE)
        self.assertEqual(flag.severity, TransferComplianceFlag.Severity.HIGH)
        self.assertEqual(
            flag.metadata["rule_type"],
            TransferRiskRule.RuleType.HIGH_AMOUNT,
        )
        self.assertEqual(flag.metadata["observed_amount"], "100.00")
        self.assertEqual(flag.metadata["threshold_amount"], "75.00")

    def test_incomplete_profile_risk_rule_can_hold_transfer(self):
        TransferRiskRule.objects.create(
            name="Profile completion hold",
            code="INCOMPLETE_PROFILE_HOLD",
            rule_type=TransferRiskRule.RuleType.INCOMPLETE_PROFILE,
            action=TransferRiskRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.MEDIUM,
        )
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        flag = transfer.compliance_flags.get(code="INCOMPLETE_PROFILE_HOLD")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.RISK_RULE)
        self.assertEqual(flag.metadata["has_profile"], False)

    def test_rapid_repeat_risk_rule_uses_recent_sender_activity(self):
        self.create_transfer(send_amount=Decimal("25.00"))
        TransferRiskRule.objects.create(
            name="Rapid repeat review",
            code="RAPID_REPEAT_REVIEW",
            source_currency=self.usd,
            rule_type=TransferRiskRule.RuleType.RAPID_REPEAT,
            repeat_count=2,
            window_minutes=60,
            action=TransferRiskRule.Action.FLAG,
            severity=TransferComplianceFlag.Severity.MEDIUM,
        )
        quote = self.create_quote(send_amount=Decimal("25.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Utilities",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.FLAGGED)
        flag = transfer.compliance_flags.get(code="RAPID_REPEAT_REVIEW")
        self.assertEqual(flag.metadata["observed_count"], "2")
        self.assertEqual(flag.metadata["window_minutes"], "60")

    def test_staff_can_add_compliance_note(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("transfer-compliance-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferComplianceEvent.Action.NOTE,
                "note": "Reviewed sender information before escalation.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        event = transfer.compliance_events.get(action=TransferComplianceEvent.Action.NOTE)
        self.assertEqual(
            event.note,
            "Reviewed sender information before escalation.",
        )
        self.assertEqual(event.performed_by, self.staff)
        audit_log = OperationalAuditLog.objects.get(
            action_name="transfer.compliance_action",
            target_id=str(transfer.id),
        )
        self.assertEqual(audit_log.actor, self.staff)
        self.assertEqual(audit_log.previous_status, Transfer.ComplianceStatus.CLEAR)
        self.assertEqual(audit_log.new_status, Transfer.ComplianceStatus.CLEAR)
        self.assertEqual(
            audit_log.metadata["compliance_action"],
            TransferComplianceEvent.Action.NOTE,
        )

    def test_staff_can_put_transfer_on_manual_compliance_hold(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("transfer-compliance-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferComplianceEvent.Action.HOLD,
                "note": "Name mismatch requires extra review.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        flag = transfer.compliance_flags.get(code="MANUAL_HOLD")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.MANUAL)
        self.assertEqual(flag.status, TransferComplianceFlag.Status.OPEN)
        event = transfer.compliance_events.get(action=TransferComplianceEvent.Action.HOLD)
        self.assertEqual(event.to_compliance_status, Transfer.ComplianceStatus.ON_HOLD)

    def test_review_and_approve_compliance_actions_are_audited(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)

        review_response = self.client.post(
            reverse("transfer-compliance-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferComplianceEvent.Action.REVIEW,
                "note": "Opening manual review.",
            },
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)

        approve_response = self.client.post(
            reverse("transfer-compliance-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferComplianceEvent.Action.APPROVE,
                "note": "Compliance checks cleared.",
            },
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.APPROVED)
        self.assertEqual(
            transfer.compliance_status,
            Transfer.ComplianceStatus.APPROVED,
        )
        self.assertTrue(
            transfer.compliance_events.filter(
                action=TransferComplianceEvent.Action.REVIEW,
            ).exists(),
        )
        self.assertTrue(
            transfer.compliance_events.filter(
                action=TransferComplianceEvent.Action.APPROVE,
            ).exists(),
        )

    def test_reject_compliance_action_requires_note(self):
        transfer = self.create_transfer(status_value=Transfer.Status.FUNDING_RECEIVED)
        self.client.force_authenticate(self.staff)
        self.client.post(
            reverse("transfer-compliance-action", kwargs={"pk": transfer.pk}),
            {
                "action": TransferComplianceEvent.Action.REVIEW,
                "note": "Opening manual review.",
            },
            format="json",
        )

        response = self.client.post(
            reverse("transfer-compliance-action", kwargs={"pk": transfer.pk}),
            {"action": TransferComplianceEvent.Action.REJECT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recipient_verification_rule_can_hold_transfer(self):
        RecipientVerificationRule.objects.create(
            name="Verified bank recipient required",
            code="RECIPIENT_VERIFY_BANK",
            destination_country=self.zambia,
            payout_method=PayoutMethod.MOBILE_MONEY,
            min_send_amount=Decimal("50.00"),
            action=RecipientVerificationRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        flag = transfer.compliance_flags.get(code="RECIPIENT_VERIFY_BANK")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.RECIPIENT)
        self.assertEqual(
            flag.metadata["recipient_verification_status"],
            "not_started",
        )
        self.assertTrue(
            transfer.notifications.filter(
                event_type=TransferNotification.EventType.VERIFICATION_REQUIRED,
                trigger_id=str(flag.id),
            ).exists(),
        )

    def test_verified_recipient_can_pass_recipient_verification_rule(self):
        self.recipient.mark_verification_reviewed(
            status=Recipient.VerificationStatus.VERIFIED,
            reviewed_by=self.staff,
        )
        RecipientVerificationRule.objects.create(
            name="Verified recipient required",
            code="RECIPIENT_VERIFY_PASS",
            destination_country=self.zambia,
            payout_method=PayoutMethod.MOBILE_MONEY,
            action=RecipientVerificationRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.MEDIUM,
        )
        quote = self.create_quote(send_amount=Decimal("75.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "School fees",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.CLEAR)
        self.assertFalse(
            transfer.compliance_flags.filter(code="RECIPIENT_VERIFY_PASS").exists(),
        )

    def test_transfer_creation_queues_sender_and_recipient_sanctions_checks(self):
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        checks = transfer.sanctions_checks.order_by("party_type")
        self.assertEqual(checks.count(), 2)
        self.assertEqual(checks[0].status, TransferSanctionsCheck.Status.QUEUED)
        self.assertEqual(checks[1].status, TransferSanctionsCheck.Status.QUEUED)

    @override_settings(
        SANCTIONS_AML_PROVIDER="screening_provider",
        SANCTIONS_AML_PROVIDER_CONFIGS={
            "screening_provider": {
                "display_name": "Screening provider",
                "api_key": "secret-screening-key",
            },
        },
    )
    def test_transfer_creation_uses_configured_sanctions_provider(self):
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        check = transfer.sanctions_checks.get(
            party_type=TransferSanctionsCheck.PartyType.RECIPIENT,
        )
        self.assertEqual(check.provider_name, "screening_provider")
        self.assertEqual(
            check.screening_payload["integration_mode"],
            "external_sanctions_aml_provider",
        )
        self.assertTrue(
            check.screening_payload["provider_config"]["api_key_configured"],
        )
        self.assertNotIn("secret-screening-key", str(check.screening_payload))

    def test_staff_can_clear_sanctions_check(self):
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)
        create_response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Bills",
            },
            format="json",
        )
        transfer = Transfer.objects.get(id=create_response.data["id"])
        check = transfer.sanctions_checks.get(
            party_type=TransferSanctionsCheck.PartyType.SENDER,
        )

        self.client.force_authenticate(self.staff)
        response = self.client.post(
            reverse(
                "transfer-sanctions-check-review",
                kwargs={"pk": transfer.pk, "check_id": check.id},
            ),
            {
                "status": TransferSanctionsCheck.Status.CLEAR,
                "provider_reference": "screening-case-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        check.refresh_from_db()
        self.assertEqual(check.status, TransferSanctionsCheck.Status.CLEAR)
        self.assertEqual(check.provider_reference, "screening-case-1")
        self.assertTrue(
            transfer.compliance_events.filter(
                action=TransferComplianceEvent.Action.SCREENING,
            ).exists(),
        )

    def test_possible_sanctions_match_puts_transfer_on_hold(self):
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)
        create_response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Rent",
            },
            format="json",
        )
        transfer = Transfer.objects.get(id=create_response.data["id"])
        check = transfer.sanctions_checks.get(
            party_type=TransferSanctionsCheck.PartyType.RECIPIENT,
        )

        self.client.force_authenticate(self.staff)
        response = self.client.post(
            reverse(
                "transfer-sanctions-check-review",
                kwargs={"pk": transfer.pk, "check_id": check.id},
            ),
            {
                "status": TransferSanctionsCheck.Status.POSSIBLE_MATCH,
                "review_note": "Name similarity requires escalation.",
                "match_score": "87.50",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        check.refresh_from_db()
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        self.assertEqual(check.status, TransferSanctionsCheck.Status.POSSIBLE_MATCH)
        flag = transfer.compliance_flags.get(code="SANCTIONS_RECIPIENT_SCREENING")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.SANCTIONS)
        self.assertEqual(
            flag.metadata["screening_status"],
            TransferSanctionsCheck.Status.POSSIBLE_MATCH,
        )

    def test_aml_large_transfer_rule_flags_transfer(self):
        TransferAmlRule.objects.create(
            name="Large transfer monitoring",
            code="AML_LARGE_TRANSFER",
            corridor=self.corridor,
            rule_type=TransferAmlRule.RuleType.LARGE_TRANSFER,
            threshold_amount=Decimal("75.00"),
            action=TransferAmlRule.Action.FLAG,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Inventory support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.FLAGGED)
        flag = transfer.compliance_flags.get(code="AML_LARGE_TRANSFER")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.AML)
        self.assertEqual(
            flag.metadata["rule_type"],
            TransferAmlRule.RuleType.LARGE_TRANSFER,
        )
        self.assertEqual(flag.metadata["observed_amount"], "100.00")

    def test_aml_velocity_volume_rule_can_hold_transfer(self):
        self.create_transfer(send_amount=Decimal("60.00"))
        TransferAmlRule.objects.create(
            name="Velocity volume hold",
            code="AML_VELOCITY_VOLUME",
            source_currency=self.usd,
            rule_type=TransferAmlRule.RuleType.VELOCITY_VOLUME,
            threshold_amount=Decimal("100.00"),
            window_minutes=60,
            action=TransferAmlRule.Action.HOLD,
            severity=TransferComplianceFlag.Severity.CRITICAL,
        )
        quote = self.create_quote(send_amount=Decimal("50.00"))
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Family support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = Transfer.objects.get(id=response.data["id"])
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        flag = transfer.compliance_flags.get(code="AML_VELOCITY_VOLUME")
        self.assertEqual(flag.category, TransferComplianceFlag.Category.AML)
        self.assertEqual(flag.metadata["window_minutes"], "60")
        self.assertEqual(flag.metadata["observed_amount"], "110.00")

    def test_staff_can_escalate_and_clear_aml_flag(self):
        TransferAmlRule.objects.create(
            name="Daily AML volume review",
            code="AML_DAILY_VOLUME",
            source_currency=self.usd,
            rule_type=TransferAmlRule.RuleType.DAILY_VOLUME,
            threshold_amount=Decimal("75.00"),
            action=TransferAmlRule.Action.FLAG,
            severity=TransferComplianceFlag.Severity.HIGH,
        )
        quote = self.create_quote(send_amount=Decimal("100.00"))
        self.client.force_authenticate(self.sender)
        create_response = self.client.post(
            reverse("transfer-list-create"),
            {
                "quote_id": str(quote.id),
                "recipient_id": str(self.recipient.id),
                "reason_for_transfer": "Urgent support",
            },
            format="json",
        )
        transfer = Transfer.objects.get(id=create_response.data["id"])
        flag = transfer.compliance_flags.get(code="AML_DAILY_VOLUME")

        self.client.force_authenticate(self.staff)
        escalate_response = self.client.post(
            reverse(
                "transfer-aml-flag-review",
                kwargs={"pk": transfer.pk, "flag_id": flag.id},
            ),
            {
                "decision": "escalate",
                "review_note": "Escalating AML pattern to the investigations queue.",
                "escalation_destination": "internal_aml_queue",
                "escalation_reference": "AML-CASE-1001",
            },
            format="json",
        )

        self.assertEqual(escalate_response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        flag.refresh_from_db()
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.ON_HOLD)
        self.assertEqual(flag.status, TransferComplianceFlag.Status.ACKNOWLEDGED)
        self.assertEqual(flag.metadata["aml_workflow_status"], "escalated")
        self.assertEqual(flag.metadata["escalation_reference"], "AML-CASE-1001")

        clear_response = self.client.post(
            reverse(
                "transfer-aml-flag-review",
                kwargs={"pk": transfer.pk, "flag_id": flag.id},
            ),
            {
                "decision": "clear",
                "review_note": "Customer history supports the transfer volume.",
            },
            format="json",
        )

        self.assertEqual(clear_response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        flag.refresh_from_db()
        self.assertEqual(flag.status, TransferComplianceFlag.Status.RESOLVED)
        self.assertEqual(transfer.compliance_status, Transfer.ComplianceStatus.CLEAR)
        self.assertTrue(
            transfer.compliance_events.filter(
                action=TransferComplianceEvent.Action.AML,
            ).exists(),
        )
