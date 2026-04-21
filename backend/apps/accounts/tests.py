from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from rest_framework.authtoken.models import Token

from apps.countries.models import Country, Currency

from .models import SenderProfile


User = get_user_model()


class StaffLoginTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="test-password-123",
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password="test-password-123",
            is_staff=True,
        )

    def test_staff_login_allows_staff_accounts(self):
        response = self.client.post(
            reverse("account-staff-login"),
            {
                "email": self.staff.email,
                "password": "test-password-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["user"]["is_staff"])
        self.assertTrue(response.data["token"])

    def test_staff_login_rejects_customer_accounts(self):
        response = self.client.post(
            reverse("account-staff-login"),
            {
                "email": self.customer.email,
                "password": "test-password-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Staff access is required.", str(response.data["detail"]))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_BASE_URL="https://app.example.com",
)
class PasswordResetTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="reset@example.com",
            password="old-password-123",
        )
        self.staff = User.objects.create_user(
            email="staff-reset@example.com",
            password="old-password-123",
            is_staff=True,
        )

    def test_password_reset_request_sends_customer_reset_link(self):
        response = self.client.post(
            reverse("account-password-reset"),
            {"email": self.customer.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://app.example.com/reset-password/confirm", mail.outbox[0].body)
        self.assertIn("uid=", mail.outbox[0].body)
        self.assertIn("token=", mail.outbox[0].body)

    def test_password_reset_request_is_generic_for_unknown_and_staff_accounts(self):
        unknown_response = self.client.post(
            reverse("account-password-reset"),
            {"email": "unknown@example.com"},
            format="json",
        )
        staff_response = self.client.post(
            reverse("account-password-reset"),
            {"email": self.staff.email},
            format="json",
        )

        self.assertEqual(unknown_response.status_code, status.HTTP_200_OK)
        self.assertEqual(staff_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_confirm_updates_password_and_clears_tokens(self):
        Token.objects.create(user=self.customer)
        uid = urlsafe_base64_encode(force_bytes(self.customer.pk))
        token = default_token_generator.make_token(self.customer)

        response = self.client.post(
            reverse("account-password-reset-confirm"),
            {
                "uid": uid,
                "token": token,
                "password": "new-password-456",
                "password_confirm": "new-password-456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("new-password-456"))
        self.assertFalse(Token.objects.filter(user=self.customer).exists())

    def test_password_reset_confirm_rejects_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.customer.pk))
        response = self.client.post(
            reverse("account-password-reset-confirm"),
            {
                "uid": uid,
                "token": "bad-token",
                "password": "new-password-456",
                "password_confirm": "new-password-456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SenderKycFlowTests(APITestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar")
        self.us = Country.objects.create(
            name="United States",
            iso_code="US",
            dialing_code="+1",
            currency=self.usd,
            is_sender_enabled=True,
        )
        self.customer = User.objects.create_user(
            email="kyc-customer@example.com",
            password="test-password-123",
            first_name="Sam",
            last_name="Sender",
        )
        self.staff = User.objects.create_user(
            email="kyc-staff@example.com",
            password="test-password-123",
            is_staff=True,
        )
        self.profile = SenderProfile.objects.create(
            user=self.customer,
            phone_number="+12025550123",
            country=self.us,
        )

    def test_customer_can_submit_complete_sender_profile_for_kyc(self):
        self.client.force_authenticate(self.customer)

        response = self.client.post(reverse("sender-kyc-submit"), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.kyc_status, SenderProfile.KycStatus.PENDING)
        self.assertIsNotNone(self.profile.kyc_submitted_at)
        self.assertEqual(response.data["kyc_status"], SenderProfile.KycStatus.PENDING)

    def test_kyc_submit_requires_complete_sender_profile(self):
        self.profile.phone_number = ""
        self.profile.save(update_fields=("phone_number", "updated_at"))
        self.client.force_authenticate(self.customer)

        response = self.client.post(reverse("sender-kyc-submit"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.kyc_status,
            SenderProfile.KycStatus.NOT_STARTED,
        )

    def test_staff_can_review_sender_kyc(self):
        self.profile.submit_kyc()
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("sender-kyc-review", kwargs={"profile_id": self.profile.id}),
            {"kyc_status": SenderProfile.KycStatus.VERIFIED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.kyc_status, SenderProfile.KycStatus.VERIFIED)
        self.assertEqual(self.profile.kyc_reviewed_by, self.staff)
        self.assertIsNotNone(self.profile.kyc_reviewed_at)

    def test_customer_cannot_review_sender_kyc(self):
        self.profile.submit_kyc()
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            reverse("sender-kyc-review", kwargs={"profile_id": self.profile.id}),
            {"kyc_status": SenderProfile.KycStatus.VERIFIED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rejected_or_needs_review_kyc_requires_staff_note(self):
        self.profile.submit_kyc()
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("sender-kyc-review", kwargs={"profile_id": self.profile.id}),
            {"kyc_status": SenderProfile.KycStatus.REJECTED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verified_kyc_reopens_when_sender_profile_changes(self):
        self.profile.mark_kyc_reviewed(
            status=SenderProfile.KycStatus.VERIFIED,
            reviewed_by=self.staff,
        )
        self.client.force_authenticate(self.customer)

        response = self.client.patch(
            reverse("sender-profile"),
            {"phone_number": "+12025550124"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.kyc_status,
            SenderProfile.KycStatus.NEEDS_REVIEW,
        )
        self.assertIn("changed after verification", self.profile.kyc_review_note)
