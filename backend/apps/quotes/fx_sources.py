from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import os
from urllib.parse import urlencode

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.countries.models import CountryCorridor
from common.integrations import (
    ProviderConfigurationError,
    ProviderRequestError,
    get_provider_config,
    redact_sensitive,
    request_json,
)

from .models import ExchangeRate


DATABASE_FX_SOURCE = "database"
FRANKFURTER_SOURCE = "frankfurter"
OPEN_EXCHANGE_RATES_SOURCE = "open_exchange_rates"
OPEN_EXCHANGE_RATES_ALIASES = {OPEN_EXCHANGE_RATES_SOURCE, "openexchangerates"}
RATE_QUANT = Decimal("0.00000001")
fx_logger = logging.getLogger("mbongopay.fx")


@dataclass(frozen=True)
class FxRateResult:
    exchange_rate: Decimal
    provider_name: str
    response_payload: dict


class BaseFxRateSource:
    code = ""
    display_name = ""

    def get_rate(self, corridor: CountryCorridor) -> FxRateResult:
        raise NotImplementedError


class DatabaseFxRateSource(BaseFxRateSource):
    code = DATABASE_FX_SOURCE
    display_name = "Database exchange rates"

    def get_rate(self, corridor: CountryCorridor) -> FxRateResult:
        now = timezone.now()
        exchange_rate = (
            ExchangeRate.objects.filter(
                corridor=corridor,
                is_active=True,
                effective_at__lte=now,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by("-effective_at", "-created_at")
            .first()
        )
        if not exchange_rate:
            raise serializers.ValidationError(
                {"corridor_id": "No exchange rate is available for this route."},
            )

        return FxRateResult(
            exchange_rate=exchange_rate.rate,
            provider_name=exchange_rate.provider_name,
            response_payload={
                "source": self.code,
                "exchange_rate_id": str(exchange_rate.id),
            },
        )


class GenericHttpFxRateSource(BaseFxRateSource):
    def __init__(self, code: str):
        self.code = code
        self.config = get_provider_config(
            "FX_RATE_SOURCE_CONFIGS",
            code,
            default_display_name=code,
        )
        self.display_name = self.config.display_name

    def get_rate(self, corridor: CountryCorridor) -> FxRateResult:
        payload = {
            "source_currency": corridor.source_currency.code,
            "destination_currency": corridor.destination_currency.code,
            "source_country": corridor.source_country.iso_code,
            "destination_country": corridor.destination_country.iso_code,
            "corridor_id": str(corridor.id),
            "provider_config": self.config.public_metadata(),
        }
        try:
            response = request_json(
                config=self.config,
                path=str(self.config.metadata.get("rate_path") or "/fx/rate"),
                payload=payload,
                method=str(self.config.metadata.get("rate_method") or "POST"),
            )
        except (ProviderConfigurationError, ProviderRequestError) as exc:
            raise serializers.ValidationError(
                {"corridor_id": "FX rate provider is unavailable."},
            ) from exc
        raw_rate = response.get("rate") or response.get("exchange_rate")
        try:
            exchange_rate = Decimal(str(raw_rate))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise serializers.ValidationError(
                {"corridor_id": "FX provider returned an invalid exchange rate."},
            ) from exc

        if exchange_rate <= 0:
            raise serializers.ValidationError(
                {"corridor_id": "FX provider returned an invalid exchange rate."},
            )

        return FxRateResult(
            exchange_rate=exchange_rate,
            provider_name=self.code,
            response_payload=redact_sensitive(response),
        )


class OpenExchangeRatesFxRateSource(BaseFxRateSource):
    code = OPEN_EXCHANGE_RATES_SOURCE
    display_name = "Open Exchange Rates"

    def __init__(self, code: str = OPEN_EXCHANGE_RATES_SOURCE):
        self.code = code
        self.config = get_provider_config(
            "FX_RATE_SOURCE_CONFIGS",
            code,
            default_display_name=self.display_name,
            defaults={"base_url": "https://openexchangerates.org/api"},
        )
        self.display_name = self.config.display_name

    def get_rate(self, corridor: CountryCorridor) -> FxRateResult:
        app_id = self.config.api_key or str(self.config.metadata.get("app_id") or "")
        if not app_id:
            fx_logger.error(
                "Missing FX provider env var provider=%s env_var=FX_RATE_SOURCE_CONFIGS "
                "expected_key=open_exchange_rates.app_id_or_api_key",
                self.code,
            )
            raise serializers.ValidationError(
                {"corridor_id": "Open Exchange Rates app_id is not configured."},
            )

        source_code = corridor.source_currency.code.upper()
        destination_code = corridor.destination_currency.code.upper()
        query_params = {
            "app_id": app_id,
            "prettyprint": "0",
        }
        if self.should_use_symbols():
            query_params["symbols"] = ",".join(
                sorted({source_code, destination_code}),
            )

        latest_path = str(self.config.metadata.get("latest_path") or "/latest.json")
        request_path = f"{latest_path}?{urlencode(query_params)}"
        try:
            response = request_json(
                config=self.config,
                path=request_path,
                method="GET",
                include_api_key_auth=False,
            )
        except (ProviderConfigurationError, ProviderRequestError) as exc:
            fx_logger.exception(
                "Open Exchange Rates fetch failed provider=%s reason=%s",
                self.code,
                exc,
            )
            raise serializers.ValidationError(
                {"corridor_id": "Open Exchange Rates is unavailable."},
            ) from exc

        if response.get("error"):
            error_message = (
                response.get("description")
                or response.get("message")
                or "Open Exchange Rates rejected the request."
            )
            raise serializers.ValidationError({"corridor_id": str(error_message)})

        rates = response.get("rates")
        if not isinstance(rates, dict):
            raise serializers.ValidationError(
                {"corridor_id": "Open Exchange Rates returned no rates."},
            )

        base_code = str(response.get("base") or "USD").upper()
        source_rate = self.get_currency_rate(rates, source_code, base_code)
        destination_rate = self.get_currency_rate(rates, destination_code, base_code)
        exchange_rate = (destination_rate / source_rate).quantize(
            RATE_QUANT,
            rounding=ROUND_HALF_UP,
        )

        if exchange_rate <= 0:
            raise serializers.ValidationError(
                {"corridor_id": "Open Exchange Rates returned an invalid rate."},
            )

        return FxRateResult(
            exchange_rate=exchange_rate,
            provider_name=self.code,
            response_payload=redact_sensitive(
                {
                    "source": self.code,
                    "provider_base": base_code,
                    "timestamp": response.get("timestamp"),
                    "source_currency_rate": str(source_rate),
                    "destination_currency_rate": str(destination_rate),
                    "provider_config": self.config.public_metadata(),
                },
            ),
        )

    def should_use_symbols(self) -> bool:
        raw_value = self.config.metadata.get("use_symbols", False)
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes"}
        return bool(raw_value)

    def get_currency_rate(
        self,
        rates: dict,
        currency_code: str,
        base_code: str,
    ) -> Decimal:
        if currency_code == base_code:
            return Decimal("1")

        raw_rate = rates.get(currency_code)
        if isinstance(raw_rate, dict):
            raw_rate = raw_rate.get("mid")

        try:
            rate = Decimal(str(raw_rate))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise serializers.ValidationError(
                {
                    "corridor_id": (
                        f"Open Exchange Rates did not return {currency_code}."
                    ),
                },
            ) from exc

        if rate <= 0:
            raise serializers.ValidationError(
                {"corridor_id": f"Open Exchange Rates returned invalid {currency_code}."},
            )
        return rate


class FrankfurterFxRateSource(BaseFxRateSource):
    code = FRANKFURTER_SOURCE
    display_name = "Frankfurter"

    def __init__(self):
        self.config = get_provider_config(
            "FX_RATE_SOURCE_CONFIGS",
            self.code,
            default_display_name=self.display_name,
            defaults={"base_url": "https://api.frankfurter.dev"},
        )
        self.display_name = self.config.display_name

    def get_rate(self, corridor: CountryCorridor) -> FxRateResult:
        source_code = corridor.source_currency.code.upper()
        destination_code = corridor.destination_currency.code.upper()
        if source_code == destination_code:
            return FxRateResult(
                exchange_rate=Decimal("1.00000000"),
                provider_name=self.code,
                response_payload={"source": self.code, "same_currency": True},
            )

        request_path = f"/v2/rate/{source_code}/{destination_code}"
        try:
            response = request_json(
                config=self.config,
                path=request_path,
                method="GET",
                include_api_key_auth=False,
            )
        except (ProviderConfigurationError, ProviderRequestError) as exc:
            fx_logger.exception(
                "Frankfurter fallback fetch failed provider=%s reason=%s",
                self.code,
                exc,
            )
            raise serializers.ValidationError(
                {"corridor_id": "Frankfurter FX fallback is unavailable."},
            ) from exc

        raw_rate = response.get("rate")
        try:
            exchange_rate = Decimal(str(raw_rate)).quantize(
                RATE_QUANT,
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise serializers.ValidationError(
                {"corridor_id": "Frankfurter returned an invalid exchange rate."},
            ) from exc

        if exchange_rate <= 0:
            raise serializers.ValidationError(
                {"corridor_id": "Frankfurter returned an invalid exchange rate."},
            )

        return FxRateResult(
            exchange_rate=exchange_rate,
            provider_name=self.code,
            response_payload=redact_sensitive(
                {
                    "source": self.code,
                    "provider_base": response.get("base"),
                    "provider_quote": response.get("quote"),
                    "date": response.get("date"),
                    "rate": str(exchange_rate),
                    "provider_config": self.config.public_metadata(),
                },
            ),
        )


def get_selected_fx_rate_source_code() -> str:
    return str(
        getattr(settings, "FX_RATE_SOURCE", None)
        or os.getenv("FX_RATE_SOURCE")
        or DATABASE_FX_SOURCE,
    )


def get_fx_rate_source() -> BaseFxRateSource:
    selected_source = get_selected_fx_rate_source_code()
    if selected_source == DATABASE_FX_SOURCE:
        return DatabaseFxRateSource()

    if selected_source == FRANKFURTER_SOURCE:
        return FrankfurterFxRateSource()

    if selected_source in OPEN_EXCHANGE_RATES_ALIASES:
        return OpenExchangeRatesFxRateSource(selected_source)

    source_configs = getattr(settings, "FX_RATE_SOURCE_CONFIGS", {}) or {}
    if selected_source in source_configs:
        return GenericHttpFxRateSource(selected_source)

    raise serializers.ValidationError(
        {"corridor_id": f"Unsupported FX rate source: {selected_source}"},
    )


def get_fx_fallback_sources(primary_source_code: str) -> list[BaseFxRateSource]:
    normalized_primary = primary_source_code.lower()
    if normalized_primary == DATABASE_FX_SOURCE:
        return []

    fallback_sources: list[BaseFxRateSource] = []
    if normalized_primary != FRANKFURTER_SOURCE:
        fallback_sources.append(FrankfurterFxRateSource())
    fallback_sources.append(DatabaseFxRateSource())
    return fallback_sources
