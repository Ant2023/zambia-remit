from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.countries.models import Country, Currency

from .models import Recipient, RecipientMobileMoneyAccount


User = get_user_model()


class RecipientVerificationFlowTests(APITestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar")
        self.zmw = Currency.objects.create(code="ZMW", name="Zambian Kwacha")
        self.zambia = Country.objects.create(
            name="Zambia",
            iso_code="ZM",
            dialing_code="+260",
            currency=self.zmw,
            is_destination_enabled=True,
        )
        self.customer = User.objects.create_user(
            email="recipient@example.com",
            password="test-password-123",
        )
        self.staff = User.objects.create_user(
            email="recipient-staff@example.com",
            password="test-password-123",
            is_staff=True,
        )
        self.recipient = Recipient.objects.create(
            sender=self.customer,
            first_name="Mary",
            last_name="Banda",
            country=self.zambia,
        )
        RecipientMobileMoneyAccount.objects.create(
            recipient=self.recipient,
            provider_name="MTN",
            mobile_number="+260971234567",
            account_name="Mary Banda",
            is_default=True,
        )

    def test_customer_can_submit_recipient_for_verification(self):
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            reverse("recipient-verification-submit", kwargs={"pk": self.recipient.id}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.recipient.refresh_from_db()
        self.assertEqual(
            self.recipient.verification_status,
            Recipient.VerificationStatus.PENDING,
        )
        self.assertTrue(response.data["is_verification_ready"])

    def test_verification_submit_requires_payout_details(self):
        self.recipient.mobile_money_accounts.all().delete()
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            reverse("recipient-verification-submit", kwargs={"pk": self.recipient.id}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.recipient.refresh_from_db()
        self.assertEqual(
            self.recipient.verification_status,
            Recipient.VerificationStatus.NOT_STARTED,
        )

    def test_staff_can_review_recipient_verification(self):
        self.recipient.submit_verification()
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("recipient-verification-review", kwargs={"pk": self.recipient.id}),
            {"verification_status": Recipient.VerificationStatus.VERIFIED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.recipient.refresh_from_db()
        self.assertEqual(
            self.recipient.verification_status,
            Recipient.VerificationStatus.VERIFIED,
        )
        self.assertEqual(self.recipient.verification_reviewed_by, self.staff)

    def test_rejected_or_needs_review_requires_staff_note(self):
        self.recipient.submit_verification()
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("recipient-verification-review", kwargs={"pk": self.recipient.id}),
            {"verification_status": Recipient.VerificationStatus.REJECTED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verified_recipient_reopens_when_details_change(self):
        self.recipient.mark_verification_reviewed(
            status=Recipient.VerificationStatus.VERIFIED,
            reviewed_by=self.staff,
        )
        self.client.force_authenticate(self.customer)

        response = self.client.patch(
            reverse("recipient-detail", kwargs={"pk": self.recipient.id}),
            {"phone_number": "+260977777777"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.recipient.refresh_from_db()
        self.assertEqual(
            self.recipient.verification_status,
            Recipient.VerificationStatus.NEEDS_REVIEW,
        )
        self.assertIn(
            "changed after verification",
            self.recipient.verification_review_note,
        )
