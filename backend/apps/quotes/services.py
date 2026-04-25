from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging

from rest_framework import serializers

from apps.countries.models import CountryCorridor
from apps.countries.services import (
    validate_corridor_payout_method,
    validate_payout_method_choice,
)

from .fx_sources import (
    DATABASE_FX_SOURCE,
    get_fx_fallback_sources,
    get_fx_rate_source,
)
from .models import FeeRule


MONEY_QUANT = Decimal("0.01")
fx_logger = logging.getLogger("mbongopay.fx")


@dataclass(frozen=True)
class RateResult:
    corridor: CountryCorridor
    exchange_rate: Decimal
    rate_source: str
    rate_provider_name: str
    is_primary_rate: bool
    is_live_rate: bool


def get_rate_for_corridor(corridor: CountryCorridor) -> RateResult:
    if not corridor.is_active:
        raise serializers.ValidationError({"corridor_id": "Selected route is not active."})

    primary_source = get_fx_rate_source()
    try:
        rate_result = primary_source.get_rate(corridor)
    except serializers.ValidationError as primary_error:
        fx_logger.exception(
            "Primary FX rate source failed provider=%s corridor_id=%s reason=%s",
            primary_source.code,
            corridor.id,
            primary_error,
        )
        for fallback_source in get_fx_fallback_sources(primary_source.code):
            try:
                fallback_result = fallback_source.get_rate(corridor)
            except serializers.ValidationError as fallback_error:
                fx_logger.exception(
                    "Fallback FX rate source failed provider=%s corridor_id=%s "
                    "reason=%s",
                    fallback_source.code,
                    corridor.id,
                    fallback_error,
                )
                continue

            fx_logger.warning(
                "Using fallback FX rate provider primary_provider=%s "
                "fallback_provider=%s corridor_id=%s",
                primary_source.code,
                fallback_source.code,
                corridor.id,
            )
            return RateResult(
                corridor=corridor,
                exchange_rate=fallback_result.exchange_rate,
                rate_source=fallback_source.code,
                rate_provider_name=fallback_result.provider_name,
                is_primary_rate=False,
                is_live_rate=fallback_source.code != DATABASE_FX_SOURCE,
            )
        raise

    return RateResult(
        corridor=corridor,
        exchange_rate=rate_result.exchange_rate,
        rate_source=primary_source.code,
        rate_provider_name=rate_result.provider_name,
        is_primary_rate=True,
        is_live_rate=primary_source.code != DATABASE_FX_SOURCE,
    )


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
        raise serializers.ValidationError(
            {
                "payout_method": (
                    "No active fee rule is configured for this route, payout "
                    "method, and amount."
                )
            },
        )

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
    validate_payout_method_choice(payout_method)
