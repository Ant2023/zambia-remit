from django.contrib import admin

from .models import (
    Transfer,
    TransferAmlRule,
    TransferComplianceEvent,
    TransferComplianceFlag,
    TransferLimitRule,
    TransferPaymentAction,
    TransferPaymentFraudRule,
    TransferPaymentInstruction,
    TransferPaymentWebhookEvent,
    TransferPayoutAttempt,
    TransferPayoutEvent,
    TransferSanctionsCheck,
    RecipientVerificationRule,
    TransferRiskRule,
    TransferStatusEvent,
)


class TransferStatusEventInline(admin.TabularInline):
    model = TransferStatusEvent
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class TransferPaymentInstructionInline(admin.TabularInline):
    model = TransferPaymentInstruction
    extra = 0
    readonly_fields = (
        "provider_reference",
        "instructions",
        "created_at",
        "updated_at",
    )


class TransferPaymentActionInline(admin.TabularInline):
    model = TransferPaymentAction
    extra = 0
    readonly_fields = ("created_at", "updated_at", "processed_at")
    fields = (
        "action",
        "status",
        "amount",
        "currency",
        "provider_action_reference",
        "reason_code",
        "requested_by",
        "processed_at",
    )


class TransferPayoutAttemptInline(admin.TabularInline):
    model = TransferPayoutAttempt
    extra = 0
    readonly_fields = (
        "provider_reference",
        "destination_snapshot",
        "request_payload",
        "response_payload",
        "created_at",
        "updated_at",
    )
    fields = (
        "attempt_number",
        "provider",
        "status",
        "provider_status",
        "amount",
        "currency",
        "provider_reference",
        "created_by",
    )


class TransferPayoutEventInline(admin.TabularInline):
    model = TransferPayoutEvent
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "action",
        "from_payout_status",
        "to_payout_status",
        "provider_event_id",
        "performed_by",
        "note",
    )


class TransferComplianceFlagInline(admin.TabularInline):
    model = TransferComplianceFlag
    extra = 0
    readonly_fields = ("created_at", "updated_at", "resolved_at")
    fields = (
        "category",
        "severity",
        "status",
        "code",
        "title",
        "created_by",
        "resolved_by",
        "resolved_at",
    )


class TransferComplianceEventInline(admin.TabularInline):
    model = TransferComplianceEvent
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "action",
        "from_compliance_status",
        "to_compliance_status",
        "from_transfer_status",
        "to_transfer_status",
        "performed_by",
        "note",
    )


class TransferSanctionsCheckInline(admin.TabularInline):
    model = TransferSanctionsCheck
    extra = 0
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
    fields = (
        "party_type",
        "status",
        "screened_name",
        "provider_name",
        "provider_reference",
        "match_score",
        "reviewed_by",
        "reviewed_at",
    )


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "sender",
        "recipient",
        "send_amount",
        "source_currency",
        "receive_amount",
        "destination_currency",
        "payout_provider",
        "status",
        "updated_at",
    )
    list_filter = (
        "status",
        "funding_status",
        "compliance_status",
        "payout_status",
        "payout_provider",
    )
    search_fields = (
        "reference",
        "sender__email",
        "recipient__first_name",
        "recipient__last_name",
    )
    readonly_fields = ("reference", "created_at", "updated_at")
    inlines = [
        TransferComplianceFlagInline,
        TransferComplianceEventInline,
        TransferSanctionsCheckInline,
        TransferPaymentInstructionInline,
        TransferPaymentActionInline,
        TransferPayoutAttemptInline,
        TransferPayoutEventInline,
        TransferStatusEventInline,
    ]


@admin.register(TransferComplianceFlag)
class TransferComplianceFlagAdmin(admin.ModelAdmin):
    list_display = (
        "transfer",
        "category",
        "severity",
        "status",
        "code",
        "created_at",
    )
    list_filter = ("category", "severity", "status")
    search_fields = ("transfer__reference", "code", "title", "description")
    readonly_fields = ("created_at", "updated_at", "resolved_at")


@admin.register(TransferComplianceEvent)
class TransferComplianceEventAdmin(admin.ModelAdmin):
    list_display = (
        "transfer",
        "action",
        "performed_by",
        "to_compliance_status",
        "to_transfer_status",
        "created_at",
    )
    list_filter = ("action", "to_compliance_status", "to_transfer_status")
    search_fields = ("transfer__reference", "performed_by__email", "note")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransferSanctionsCheck)
class TransferSanctionsCheckAdmin(admin.ModelAdmin):
    list_display = (
        "transfer",
        "party_type",
        "status",
        "provider_name",
        "provider_reference",
        "reviewed_at",
    )
    list_filter = ("party_type", "status", "provider_name")
    search_fields = ("transfer__reference", "screened_name", "provider_reference")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")


@admin.register(RecipientVerificationRule)
class RecipientVerificationRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "destination_country",
        "payout_method",
        "min_send_amount",
        "action",
        "severity",
        "is_active",
    )
    list_filter = (
        "is_active",
        "action",
        "severity",
        "destination_country",
        "payout_method",
        "source_currency",
    )
    search_fields = ("code", "name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransferAmlRule)
class TransferAmlRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "rule_type",
        "action",
        "severity",
        "is_active",
    )
    list_filter = (
        "is_active",
        "rule_type",
        "action",
        "severity",
        "payout_method",
        "source_currency",
        "destination_country",
    )
    search_fields = ("code", "name", "description", "sender__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransferLimitRule)
class TransferLimitRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "period",
        "max_send_amount",
        "action",
        "severity",
        "is_active",
    )
    list_filter = (
        "is_active",
        "period",
        "action",
        "severity",
        "payout_method",
        "source_currency",
    )
    search_fields = ("code", "name", "description", "sender__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransferRiskRule)
class TransferRiskRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "rule_type",
        "action",
        "severity",
        "is_active",
    )
    list_filter = (
        "is_active",
        "rule_type",
        "action",
        "severity",
        "payout_method",
        "source_currency",
        "destination_country",
    )
    search_fields = ("code", "name", "description", "sender__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransferPaymentFraudRule)
class TransferPaymentFraudRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "rule_type",
        "payment_method",
        "action",
        "severity",
        "is_active",
    )
    list_filter = (
        "is_active",
        "rule_type",
        "payment_method",
        "action",
        "severity",
        "payout_method",
        "source_currency",
        "destination_country",
    )
    search_fields = ("code", "name", "description", "sender__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransferPaymentInstruction)
class TransferPaymentInstructionAdmin(admin.ModelAdmin):
    list_display = (
        "transfer",
        "payment_method",
        "provider_name",
        "amount",
        "currency",
        "status",
        "updated_at",
    )
    list_filter = ("payment_method", "provider_name", "status")


@admin.register(TransferPaymentAction)
class TransferPaymentActionAdmin(admin.ModelAdmin):
    list_display = (
        "transfer",
        "action",
        "status",
        "amount",
        "currency",
        "provider_name",
        "requested_by",
        "processed_at",
    )
    list_filter = ("action", "status", "provider_name", "currency")
    search_fields = (
        "transfer__reference",
        "provider_reference",
        "provider_action_reference",
        "reason_code",
        "note",
    )
    readonly_fields = ("created_at", "updated_at", "processed_at")


@admin.register(TransferPaymentWebhookEvent)
class TransferPaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "provider_name",
        "provider_event_id",
        "provider_reference",
        "processing_status",
        "resulting_payment_status",
        "processed_at",
    )
    list_filter = ("provider_name", "processing_status", "resulting_payment_status")
    search_fields = ("provider_event_id", "provider_reference", "processing_message")
    readonly_fields = ("created_at", "updated_at", "processed_at")


@admin.register(TransferPayoutAttempt)
class TransferPayoutAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "transfer",
        "attempt_number",
        "provider",
        "amount",
        "currency",
        "status",
        "provider_status",
        "updated_at",
    )
    list_filter = ("status", "provider", "payout_method", "currency")
    search_fields = (
        "transfer__reference",
        "provider_reference",
        "status_reason",
    )
    readonly_fields = (
        "provider_reference",
        "destination_snapshot",
        "request_payload",
        "response_payload",
        "created_at",
        "updated_at",
    )


@admin.register(TransferPayoutEvent)
class TransferPayoutEventAdmin(admin.ModelAdmin):
    list_display = (
        "transfer",
        "payout_attempt",
        "action",
        "to_payout_status",
        "provider_event_id",
        "performed_by",
        "created_at",
    )
    list_filter = ("action", "to_payout_status")
    search_fields = (
        "transfer__reference",
        "provider_event_id",
        "note",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransferStatusEvent)
class TransferStatusEventAdmin(admin.ModelAdmin):
    list_display = ("transfer", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status",)
    search_fields = ("transfer__reference", "changed_by__email")
    readonly_fields = ("created_at", "updated_at")
