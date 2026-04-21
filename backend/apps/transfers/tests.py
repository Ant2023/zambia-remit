from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.countries.models import Country, CountryCorridor, Currency
from apps.quotes.models import ExchangeRate, FeeRule, Quote
from apps.quotes.services import calculate_fee_amount, get_rate_for_corridor
from apps.recipients.models import Recipient, RecipientMobileMoneyAccount
from common.choices import PayoutMethod

from .models import (
    RecipientVerificationRule,
    Transfer,
    TransferAmlRule,
    TransferComplianceEvent,
    TransferComplianceFlag,
    TransferLimitRule,
    TransferPaymentInstruction,
    TransferPaymentWebhookEvent,
    TransferRiskRule,
    TransferSanctionsCheck,
)
from .services import apply_payment_instruction_status


User = get_user_model()


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
            send_amount=quote.send_amount,
            fee_amount=quote.fee_amount,
            exchange_rate=quote.exchange_rate,
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
        self.assertEqual(transfer.status, Transfer.Status.FUNDING_RECEIVED)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.RECEIVED)
        self.assertEqual(instruction.status, TransferPaymentInstruction.Status.PAID)
        self.assertTrue(
            transfer.status_events.filter(
                to_status=Transfer.Status.FUNDING_RECEIVED,
            ).exists(),
        )

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
        self.assertEqual(len(instruction.instructions["card_fields"]), 5)
        self.assertEqual(instruction.instructions["test_cards"][0]["outcome"], "authorized")

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
        self.assertEqual(transfer.status, Transfer.Status.FUNDING_RECEIVED)
        self.assertEqual(transfer.funding_status, Transfer.FundingStatus.RECEIVED)
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
        self.assertEqual(transfer.payout_status, Transfer.PayoutStatus.PAID)
        self.assertEqual(
            transfer.status_events.filter(to_status=Transfer.Status.COMPLETED).count(),
            1,
        )

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
