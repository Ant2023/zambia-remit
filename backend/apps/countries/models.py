from django.db import models

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
