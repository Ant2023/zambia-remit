from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.countries.models import CountryCorridor
from apps.countries.serializers import CountrySerializer, CurrencySerializer
from apps.recipients.models import Recipient

from .models import FeeRule, Quote
from .services import (
    calculate_fee_amount,
    calculate_receive_amount,
    get_rate_for_corridor,
    validate_corridor_payout_method,
    validate_payout_method,
    validate_send_amount,
)


class FeeRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeRule
        fields = (
            "id",
            "corridor",
            "payout_method",
            "min_amount",
            "max_amount",
            "fixed_fee",
            "percentage_fee",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class QuoteSerializer(serializers.ModelSerializer):
    corridor_id = serializers.UUIDField(write_only=True)
    recipient_id = serializers.UUIDField(
        write_only=True,
        required=False,
        allow_null=True,
    )
    source_country = CountrySerializer(read_only=True)
    destination_country = CountrySerializer(read_only=True)
    source_currency = CurrencySerializer(read_only=True)
    destination_currency = CurrencySerializer(read_only=True)

    class Meta:
        model = Quote
        fields = (
            "id",
            "corridor_id",
            "recipient_id",
            "recipient",
            "source_country",
            "destination_country",
            "source_currency",
            "destination_currency",
            "payout_method",
            "send_amount",
            "fee_amount",
            "exchange_rate",
            "rate_source",
            "rate_provider_name",
            "is_primary_rate",
            "is_live_rate",
            "receive_amount",
            "status",
            "expires_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "recipient",
            "source_country",
            "destination_country",
            "source_currency",
            "destination_currency",
            "fee_amount",
            "exchange_rate",
            "rate_source",
            "rate_provider_name",
            "is_primary_rate",
            "is_live_rate",
            "receive_amount",
            "status",
            "expires_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        request = self.context["request"]
        corridor_id = attrs.pop("corridor_id")
        recipient_id = attrs.pop("recipient_id", None)
        send_amount = attrs["send_amount"]
        payout_method = attrs["payout_method"]

        try:
            corridor = CountryCorridor.objects.select_related(
                "source_country",
                "destination_country",
                "source_currency",
                "destination_currency",
            ).get(id=corridor_id, is_active=True)
        except CountryCorridor.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"corridor_id": "Selected route is not available."},
            ) from exc

        if not corridor.source_country.is_sender_enabled:
            raise serializers.ValidationError(
                {"corridor_id": "Sender country is not currently enabled."},
            )

        if not corridor.destination_country.is_destination_enabled:
            raise serializers.ValidationError(
                {"corridor_id": "Destination country is not currently enabled."},
            )

        validate_send_amount(corridor, send_amount)
        validate_corridor_payout_method(corridor, payout_method, send_amount)
        rate_result = get_rate_for_corridor(corridor)

        recipient = None
        if recipient_id:
            try:
                recipient = Recipient.objects.get(id=recipient_id, sender=request.user)
            except Recipient.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {"recipient_id": "Recipient not found."},
                ) from exc

            if recipient.country_id != corridor.destination_country_id:
                raise serializers.ValidationError(
                    {"recipient_id": "Recipient country must match the destination."},
                )

        attrs["corridor"] = corridor
        attrs["recipient"] = recipient
        attrs["backend_exchange_rate"] = rate_result.exchange_rate
        attrs["backend_rate_source"] = rate_result.rate_source
        attrs["backend_rate_provider_name"] = rate_result.rate_provider_name
        attrs["backend_is_primary_rate"] = rate_result.is_primary_rate
        attrs["backend_is_live_rate"] = rate_result.is_live_rate
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        corridor = validated_data.pop("corridor")
        exchange_rate = validated_data.pop("backend_exchange_rate")
        rate_source = validated_data.pop("backend_rate_source")
        rate_provider_name = validated_data.pop("backend_rate_provider_name")
        is_primary_rate = validated_data.pop("backend_is_primary_rate")
        is_live_rate = validated_data.pop("backend_is_live_rate")
        send_amount = validated_data["send_amount"]
        payout_method = validated_data["payout_method"]

        fee_amount = calculate_fee_amount(corridor, payout_method, send_amount)
        receive_amount = calculate_receive_amount(send_amount, exchange_rate)

        return Quote.objects.create(
            sender=request.user,
            recipient=validated_data.get("recipient"),
            source_country=corridor.source_country,
            destination_country=corridor.destination_country,
            source_currency=corridor.source_currency,
            destination_currency=corridor.destination_currency,
            payout_method=payout_method,
            send_amount=send_amount,
            fee_amount=fee_amount,
            exchange_rate=exchange_rate,
            rate_source=rate_source,
            rate_provider_name=rate_provider_name,
            is_primary_rate=is_primary_rate,
            is_live_rate=is_live_rate,
            receive_amount=receive_amount,
            expires_at=timezone.now() + timedelta(minutes=15),
        )


class RateEstimateQuerySerializer(serializers.Serializer):
    source_country_id = serializers.UUIDField()
    destination_country_id = serializers.UUIDField()
    send_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    payout_method = serializers.ChoiceField(
        choices=(("mobile_money", "Mobile money"), ("bank_deposit", "Bank deposit")),
        required=False,
        default="mobile_money",
    )


class RateEstimateSerializer(serializers.Serializer):
    corridor_id = serializers.UUIDField()
    source_country = CountrySerializer()
    destination_country = CountrySerializer()
    source_currency = CurrencySerializer()
    destination_currency = CurrencySerializer()
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8)
    rate_source = serializers.CharField()
    rate_provider_name = serializers.CharField()
    is_primary_rate = serializers.BooleanField()
    is_live_rate = serializers.BooleanField()
    min_send_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    max_send_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    send_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    fee_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    receive_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    total_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )


def build_rate_payload(
    corridor,
    exchange_rate,
    *,
    rate_source,
    rate_provider_name,
    is_primary_rate,
    is_live_rate,
    send_amount=None,
    payout_method=None,
):
    fee_amount = None
    receive_amount = None
    total_amount = None

    if send_amount is not None:
        method = payout_method or "mobile_money"
        receive_amount = calculate_receive_amount(send_amount, exchange_rate)

        if corridor.min_send_amount <= send_amount <= corridor.max_send_amount:
            validate_send_amount(corridor, send_amount)
            validate_corridor_payout_method(corridor, method, send_amount)
            fee_amount = calculate_fee_amount(corridor, method, send_amount)
            total_amount = (send_amount + fee_amount).quantize(Decimal("0.01"))
        else:
            validate_payout_method(method)
            validate_corridor_payout_method(corridor, method)
    elif payout_method is not None:
        validate_payout_method(payout_method)
        validate_corridor_payout_method(corridor, payout_method)

    return {
        "corridor_id": corridor.id,
        "source_country": corridor.source_country,
        "destination_country": corridor.destination_country,
        "source_currency": corridor.source_currency,
        "destination_currency": corridor.destination_currency,
        "exchange_rate": exchange_rate,
        "rate_source": rate_source,
        "rate_provider_name": rate_provider_name,
        "is_primary_rate": is_primary_rate,
        "is_live_rate": is_live_rate,
        "min_send_amount": corridor.min_send_amount,
        "max_send_amount": corridor.max_send_amount,
        "send_amount": send_amount,
        "fee_amount": fee_amount,
        "receive_amount": receive_amount,
        "total_amount": total_amount,
    }
