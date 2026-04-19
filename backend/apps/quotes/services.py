from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from apps.countries.models import CountryCorridor
from common.choices import PayoutMethod

from .models import FeeRule


MONEY_QUANT = Decimal("0.01")

STATIC_ZMW_RATES = {
    "USD": Decimal("25.50000000"),
    "GBP": Decimal("32.25000000"),
    "EUR": Decimal("27.40000000"),
}


@dataclass(frozen=True)
class RateResult:
    corridor: CountryCorridor
    exchange_rate: Decimal


def get_rate_for_corridor(corridor: CountryCorridor) -> RateResult:
    if not corridor.is_active:
        raise serializers.ValidationError({"corridor_id": "Selected route is not active."})

    if corridor.destination_currency.code != "ZMW":
        raise serializers.ValidationError(
            {"destination_country_id": "Only Zambia is supported at this time."},
        )

    exchange_rate = STATIC_ZMW_RATES.get(corridor.source_currency.code)
    if not exchange_rate:
        raise serializers.ValidationError(
            {"source_country_id": "No exchange rate is available for this sender country."},
        )

    return RateResult(corridor=corridor, exchange_rate=exchange_rate)


def get_active_corridor(source_country_id: str, destination_country_id: str):
    try:
        corridor = CountryCorridor.objects.select_related(
            "source_country",
            "destination_country",
            "source_currency",
            "destination_currency",
        ).get(
            source_country_id=source_country_id,
            destination_country_id=destination_country_id,
            is_active=True,
        )
    except CountryCorridor.DoesNotExist as exc:
        raise serializers.ValidationError(
            {"destination_country_id": "This country pair is not currently supported."},
        ) from exc

    if not corridor.source_country.is_sender_enabled:
        raise serializers.ValidationError(
            {"source_country_id": "This sender country is not currently enabled."},
        )

    if not corridor.destination_country.is_destination_enabled:
        raise serializers.ValidationError(
            {"destination_country_id": "This destination country is not currently enabled."},
        )

    return corridor


def validate_send_amount(corridor: CountryCorridor, send_amount: Decimal) -> None:
    if send_amount < corridor.min_send_amount:
        raise serializers.ValidationError(
            {"send_amount": f"Minimum send amount is {corridor.min_send_amount}."},
        )

    if send_amount > corridor.max_send_amount:
        raise serializers.ValidationError(
            {"send_amount": f"Maximum send amount is {corridor.max_send_amount}."},
        )


def calculate_fee_amount(
    corridor: CountryCorridor,
    payout_method: str,
    send_amount: Decimal,
) -> Decimal:
    fee_rule = (
        FeeRule.objects.filter(
            corridor=corridor,
            payout_method=payout_method,
            is_active=True,
            min_amount__lte=send_amount,
            max_amount__gte=send_amount,
        )
        .order_by("min_amount")
        .first()
    )

    if not fee_rule:
        return Decimal("0.00")

    percentage_fee = send_amount * (fee_rule.percentage_fee / Decimal("100"))
    return (fee_rule.fixed_fee + percentage_fee).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


def calculate_receive_amount(send_amount: Decimal, exchange_rate: Decimal) -> Decimal:
    return (send_amount * exchange_rate).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


def validate_payout_method(payout_method: str) -> None:
    if payout_method not in PayoutMethod.values:
        raise serializers.ValidationError({"payout_method": "Unsupported payout method."})
