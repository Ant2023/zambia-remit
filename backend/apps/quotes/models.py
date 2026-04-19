from django.conf import settings
from django.db import models

from common.choices import PayoutMethod
from common.models import BaseModel


class FeeRule(BaseModel):
    corridor = models.ForeignKey(
        "countries.CountryCorridor",
        on_delete=models.CASCADE,
        related_name="fee_rules",
    )
    payout_method = models.CharField(max_length=24, choices=PayoutMethod.choices)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fixed_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    percentage_fee = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("corridor", "payout_method", "min_amount")
        indexes = [
            models.Index(fields=("corridor", "payout_method", "is_active")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_amount__gte=0),
                name="fee_rule_min_amount_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(max_amount__gte=models.F("min_amount")),
                name="fee_rule_max_amount_gte_min",
            ),
            models.CheckConstraint(
                condition=models.Q(fixed_fee__gte=0),
                name="fee_rule_fixed_fee_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(percentage_fee__gte=0),
                name="fee_rule_percentage_fee_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.corridor} {self.payout_method}"


class Quote(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        USED = "used", "Used"
        CANCELLED = "cancelled", "Cancelled"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quotes",
    )
    recipient = models.ForeignKey(
        "recipients.Recipient",
        on_delete=models.SET_NULL,
        related_name="quotes",
        null=True,
        blank=True,
    )
    source_country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="source_quotes",
    )
    destination_country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="destination_quotes",
    )
    source_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="source_quotes",
    )
    destination_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="destination_quotes",
    )
    payout_method = models.CharField(max_length=24, choices=PayoutMethod.choices)
    send_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8)
    receive_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("sender", "status")),
            models.Index(fields=("source_country", "destination_country", "payout_method")),
            models.Index(fields=("expires_at",)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(send_amount__gt=0),
                name="quote_send_amount_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(fee_amount__gte=0),
                name="quote_fee_amount_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(exchange_rate__gt=0),
                name="quote_exchange_rate_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(receive_amount__gt=0),
                name="quote_receive_amount_gt_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.send_amount} {self.source_currency} to {self.destination_currency}"
