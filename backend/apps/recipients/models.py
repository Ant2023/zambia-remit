from django.conf import settings
from django.db import models

from common.models import BaseModel


class Recipient(BaseModel):
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

    class Meta:
        ordering = ("first_name", "last_name")
        indexes = [
            models.Index(fields=("sender", "country")),
            models.Index(fields=("sender", "last_name", "first_name")),
        ]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

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
