from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import BaseModel


class Recipient(BaseModel):
    class VerificationStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PENDING = "pending", "Pending"
        NEEDS_REVIEW = "needs_review", "Needs review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recipients",
    )
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=32, blank=True)
    country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="recipients",
    )
    relationship_to_sender = models.CharField(max_length=80, blank=True)
    verification_status = models.CharField(
        max_length=24,
        choices=VerificationStatus.choices,
        default=VerificationStatus.NOT_STARTED,
    )
    verification_submitted_at = models.DateTimeField(null=True, blank=True)
    verification_reviewed_at = models.DateTimeField(null=True, blank=True)
    verification_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_recipients",
        null=True,
        blank=True,
    )
    verification_review_note = models.TextField(blank=True)

    class Meta:
        ordering = ("first_name", "last_name")
        indexes = [
            models.Index(fields=("sender", "country")),
            models.Index(fields=("sender", "last_name", "first_name")),
            models.Index(fields=("verification_status", "verification_submitted_at")),
        ]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def has_payout_account(self) -> bool:
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "mobile_money_accounts" in prefetched or "bank_accounts" in prefetched:
            return bool(
                prefetched.get("mobile_money_accounts", [])
                or prefetched.get("bank_accounts", []),
            )

        return (
            self.mobile_money_accounts.exists()
            or self.bank_accounts.exists()
        )

    @property
    def is_verification_ready(self) -> bool:
        return bool(
            self.first_name
            and self.last_name
            and self.country_id
            and self.has_payout_account
        )

    def submit_verification(self) -> None:
        self.verification_status = self.VerificationStatus.PENDING
        self.verification_submitted_at = timezone.now()
        self.verification_reviewed_at = None
        self.verification_reviewed_by = None
        self.verification_review_note = ""
        self.save(
            update_fields=(
                "verification_status",
                "verification_submitted_at",
                "verification_reviewed_at",
                "verification_reviewed_by",
                "verification_review_note",
                "updated_at",
            ),
        )

    def mark_verification_reviewed(
        self,
        *,
        status: str,
        reviewed_by,
        note: str = "",
    ) -> None:
        self.verification_status = status
        self.verification_reviewed_at = timezone.now()
        self.verification_reviewed_by = reviewed_by
        self.verification_review_note = note
        self.save(
            update_fields=(
                "verification_status",
                "verification_reviewed_at",
                "verification_reviewed_by",
                "verification_review_note",
                "updated_at",
            ),
        )

    def __str__(self) -> str:
        return self.full_name


class RecipientMobileMoneyAccount(BaseModel):
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name="mobile_money_accounts",
    )
    provider_name = models.CharField(max_length=120)
    mobile_number = models.CharField(max_length=32)
    account_name = models.CharField(max_length=180, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ("provider_name", "mobile_number")
        indexes = [
            models.Index(fields=("recipient", "is_default")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "provider_name", "mobile_number"),
                name="unique_recipient_mobile_money_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_name} - {self.mobile_number}"


class RecipientBankAccount(BaseModel):
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name="bank_accounts",
    )
    bank_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=80)
    account_name = models.CharField(max_length=180, blank=True)
    branch_name = models.CharField(max_length=120, blank=True)
    swift_code = models.CharField(max_length=32, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ("bank_name", "account_number")
        indexes = [
            models.Index(fields=("recipient", "is_default")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "bank_name", "account_number"),
                name="unique_recipient_bank_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bank_name} - {self.account_number}"
