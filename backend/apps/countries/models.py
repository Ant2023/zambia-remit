from django.db import models

from common.choices import PayoutMethod
from common.models import BaseModel


class Currency(BaseModel):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=64)
    minor_unit = models.PositiveSmallIntegerField(default=2)

    class Meta:
        ordering = ("code",)
        verbose_name_plural = "currencies"

    def __str__(self) -> str:
        return self.code


class Country(BaseModel):
    name = models.CharField(max_length=120)
    iso_code = models.CharField(max_length=2, unique=True)
    dialing_code = models.CharField(max_length=8, blank=True)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="countries",
    )
    is_sender_enabled = models.BooleanField(default=False)
    is_destination_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "countries"
        indexes = [
            models.Index(fields=("is_sender_enabled", "is_destination_enabled")),
        ]

    def __str__(self) -> str:
        return self.name


class CountryCorridor(BaseModel):
    source_country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="outgoing_corridors",
    )
    destination_country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="incoming_corridors",
    )
    source_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="source_corridors",
    )
    destination_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="destination_corridors",
    )
    is_active = models.BooleanField(default=True)
    min_send_amount = models.DecimalField(max_digits=12, decimal_places=2)
    max_send_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("source_country__name", "destination_country__name")
        indexes = [
            models.Index(fields=("source_country", "destination_country", "is_active")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("source_country", "destination_country"),
                name="unique_country_corridor",
            ),
            models.CheckConstraint(
                condition=models.Q(min_send_amount__gte=0),
                name="corridor_min_send_amount_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(max_send_amount__gte=models.F("min_send_amount")),
                name="corridor_max_send_amount_gte_min",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_country} to {self.destination_country}"


class PayoutProvider(BaseModel):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    payout_method = models.CharField(max_length=32, choices=PayoutMethod.choices)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("payout_method", "name")
        indexes = [
            models.Index(fields=("payout_method", "is_active")),
        ]

    def __str__(self) -> str:
        return self.name


class CorridorPayoutMethod(BaseModel):
    corridor = models.ForeignKey(
        CountryCorridor,
        on_delete=models.CASCADE,
        related_name="payout_methods",
    )
    payout_method = models.CharField(max_length=32, choices=PayoutMethod.choices)
    is_active = models.BooleanField(default=True)
    min_send_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    max_send_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    display_order = models.PositiveSmallIntegerField(default=100)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("display_order", "payout_method")
        indexes = [
            models.Index(fields=("corridor", "payout_method", "is_active")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("corridor", "payout_method"),
                name="unique_corridor_payout_method",
            ),
            models.CheckConstraint(
                condition=models.Q(min_send_amount__isnull=True)
                | models.Q(min_send_amount__gte=0),
                name="corridor_payout_method_min_send_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(max_send_amount__isnull=True)
                | models.Q(min_send_amount__isnull=True)
                | models.Q(max_send_amount__gte=models.F("min_send_amount")),
                name="corridor_payout_method_max_gte_min",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.corridor} - {self.get_payout_method_display()}"


class CorridorPayoutProvider(BaseModel):
    corridor_payout_method = models.ForeignKey(
        CorridorPayoutMethod,
        on_delete=models.CASCADE,
        related_name="providers",
    )
    provider = models.ForeignKey(
        PayoutProvider,
        on_delete=models.PROTECT,
        related_name="corridor_routes",
    )
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=100)
    min_send_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    max_send_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("priority", "provider__name")
        indexes = [
            models.Index(fields=("corridor_payout_method", "is_active", "priority")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("corridor_payout_method", "provider"),
                name="unique_corridor_payout_provider",
            ),
            models.CheckConstraint(
                condition=models.Q(min_send_amount__isnull=True)
                | models.Q(min_send_amount__gte=0),
                name="corridor_payout_provider_min_send_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(max_send_amount__isnull=True)
                | models.Q(min_send_amount__isnull=True)
                | models.Q(max_send_amount__gte=models.F("min_send_amount")),
                name="corridor_payout_provider_max_gte_min",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.corridor_payout_method} via {self.provider}"
