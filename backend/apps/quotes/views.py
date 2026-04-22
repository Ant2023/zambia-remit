from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .fx_sources import DATABASE_FX_SOURCE, DatabaseFxRateSource
from .models import FeeRule, Quote
from .serializers import (
    FeeRuleSerializer,
    QuoteSerializer,
    RateEstimateQuerySerializer,
    RateEstimateSerializer,
    build_rate_payload,
)
from .services import RateResult, get_active_corridor, get_rate_for_corridor


class FeeRuleListView(generics.ListAPIView):
    queryset = FeeRule.objects.select_related("corridor").filter(is_active=True)
    serializer_class = FeeRuleSerializer
    permission_classes = [permissions.AllowAny]


class QuoteListCreateView(generics.ListCreateAPIView):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Quote.objects.select_related(
            "recipient",
            "source_country__currency",
            "destination_country__currency",
            "source_currency",
            "destination_currency",
        ).filter(sender=self.request.user)


class RateEstimateView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query_serializer = RateEstimateQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        data = query_serializer.validated_data

        corridor = get_active_corridor(
            data["source_country_id"],
            data["destination_country_id"],
        )
        rate_result = self.get_rate_result(corridor)

        payload = build_rate_payload(
            corridor=rate_result.corridor,
            exchange_rate=rate_result.exchange_rate,
            send_amount=data.get("send_amount"),
            payout_method=data.get("payout_method"),
        )
        response_serializer = RateEstimateSerializer(payload)
        return Response(response_serializer.data)

    def get_rate_result(self, corridor):
        try:
            return get_rate_for_corridor(corridor)
        except Exception as exc:
            fallback_result = DatabaseFxRateSource().get_rate(corridor)
            fallback_payload = fallback_result.response_payload
            if fallback_payload.get("source") != DATABASE_FX_SOURCE:
                raise
            return RateResult(
                corridor=corridor,
                exchange_rate=fallback_result.exchange_rate,
            )
