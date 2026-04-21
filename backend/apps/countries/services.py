from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q
from rest_framework import serializers

from common.choices import PayoutMethod

from .models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    CountryCorridor,
    PayoutProvider,
)


@dataclass(frozen=True)
class PayoutProviderSelection:
    corridor: CountryCorridor
    payout_method_route: CorridorPayoutMethod
    provider_route: CorridorPayoutProvider
    provider: PayoutProvider


def validate_payout_method_choice(payout_method: str) -> None:
    if payout_method not in PayoutMethod.values:
        raise serializers.ValidationError({"payout_method": "Unsupported payout method."})


def get_corridor_payout_method(
    corridor: CountryCorridor,
    payout_method: str,
    send_amount: Decimal | None = None,
) -> CorridorPayoutMethod:
    validate_payout_method_choice(payout_method)

    routes = CorridorPayoutMethod.objects.filter(
        corridor=corridor,
        payout_method=payout_method,
        is_active=True,
    )
    if send_amount is not None:
        routes = routes.filter(
            Q(min_send_amount__isnull=True) | Q(min_send_amount__lte=send_amount),
            Q(max_send_amount__isnull=True) | Q(max_send_amount__gte=send_amount),
        )

    route = routes.order_by("display_order", "created_at").first()
    if route is None:
        raise serializers.ValidationError(
            {"payout_method": "This payout method is not available for this route."},
        )

    return route


def select_payout_provider(
    corridor: CountryCorridor,
    payout_method: str,
    send_amount: Decimal | None = None,
) -> PayoutProviderSelection:
    payout_method_route = get_corridor_payout_method(
        corridor,
        payout_method,
        send_amount,
    )

    provider_routes = CorridorPayoutProvider.objects.select_related("provider").filter(
        corridor_payout_method=payout_method_route,
        is_active=True,
        provider__is_active=True,
        provider__payout_method=payout_method,
    )
    if send_amount is not None:
        provider_routes = provider_routes.filter(
            Q(min_send_amount__isnull=True) | Q(min_send_amount__lte=send_amount),
            Q(max_send_amount__isnull=True) | Q(max_send_amount__gte=send_amount),
        )

    provider_route = provider_routes.order_by("priority", "provider__name").first()
    if provider_route is None:
        raise serializers.ValidationError(
            {"payout_method": "No active payout provider is available for this route."},
        )

    return PayoutProviderSelection(
        corridor=corridor,
        payout_method_route=payout_method_route,
        provider_route=provider_route,
        provider=provider_route.provider,
    )


def validate_corridor_payout_method(
    corridor: CountryCorridor,
    payout_method: str,
    send_amount: Decimal | None = None,
) -> None:
    select_payout_provider(corridor, payout_method, send_amount)
