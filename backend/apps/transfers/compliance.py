from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import SenderProfile
from apps.countries.models import CountryCorridor
from apps.recipients.models import Recipient

from .models import (
    RecipientVerificationRule,
    Transfer,
    TransferAmlRule,
    TransferComplianceEvent,
    TransferComplianceFlag,
    TransferLimitRule,
    TransferRiskRule,
    TransferSanctionsCheck,
)
from .sanctions_providers import get_sanctions_aml_provider
from .services import record_compliance_event, transition_transfer_status


FINAL_TRANSFER_STATUSES = {
    Transfer.Status.CANCELLED,
    Transfer.Status.FAILED,
    Transfer.Status.REJECTED,
    Transfer.Status.REFUNDED,
}


@dataclass(frozen=True)
class LimitBreach:
    rule: TransferLimitRule
    observed_amount: Decimal


@dataclass(frozen=True)
class RiskRuleBreach:
    rule: TransferRiskRule
    observed_value: str
    details: dict


@dataclass(frozen=True)
class RecipientVerificationBreach:
    rule: RecipientVerificationRule
    recipient_status: str


@dataclass(frozen=True)
class AmlRuleBreach:
    rule: TransferAmlRule
    observed_value: str
    details: dict


def evaluate_transfer_compliance(
    transfer: Transfer,
    *,
    changed_by=None,
) -> list[TransferComplianceFlag]:
    ensure_transfer_sanctions_checks(transfer, changed_by=changed_by)
    return [
        *evaluate_transfer_limits(transfer, changed_by=changed_by),
        *evaluate_transfer_risk_rules(transfer, changed_by=changed_by),
        *evaluate_transfer_aml_rules(transfer, changed_by=changed_by),
        *evaluate_recipient_verification_rules(transfer, changed_by=changed_by),
    ]


def evaluate_transfer_limits(
    transfer: Transfer,
    *,
    changed_by=None,
) -> list[TransferComplianceFlag]:
    breaches = [
        breach
        for rule in get_matching_limit_rules(transfer)
        if (breach := evaluate_limit_rule(rule, transfer)) is not None
    ]

    if not breaches:
        return []

    with transaction.atomic():
        flags = [
            create_limit_flag(transfer, breach, changed_by=changed_by)
            for breach in breaches
        ]
        open_flags = [flag for flag in flags if flag is not None]

        if any(
            breach.rule.action == TransferLimitRule.Action.HOLD
            for breach in breaches
        ):
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
        elif transfer.compliance_status == Transfer.ComplianceStatus.CLEAR:
            transfer.compliance_status = Transfer.ComplianceStatus.FLAGGED

        transfer.save(update_fields=("compliance_status", "updated_at"))
        return open_flags


def evaluate_transfer_risk_rules(
    transfer: Transfer,
    *,
    changed_by=None,
) -> list[TransferComplianceFlag]:
    breaches = [
        breach
        for rule in get_matching_risk_rules(transfer)
        if (breach := evaluate_risk_rule(rule, transfer)) is not None
    ]

    if not breaches:
        return []

    with transaction.atomic():
        flags = [
            create_risk_rule_flag(transfer, breach, changed_by=changed_by)
            for breach in breaches
        ]
        open_flags = [flag for flag in flags if flag is not None]

        if any(
            breach.rule.action == TransferRiskRule.Action.HOLD
            for breach in breaches
        ):
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
        elif transfer.compliance_status == Transfer.ComplianceStatus.CLEAR:
            transfer.compliance_status = Transfer.ComplianceStatus.FLAGGED

        transfer.save(update_fields=("compliance_status", "updated_at"))
        return open_flags


def evaluate_transfer_aml_rules(
    transfer: Transfer,
    *,
    changed_by=None,
) -> list[TransferComplianceFlag]:
    breaches = [
        breach
        for rule in get_matching_aml_rules(transfer)
        if (breach := evaluate_aml_rule(rule, transfer)) is not None
    ]

    if not breaches:
        return []

    with transaction.atomic():
        flags = [
            create_aml_flag(transfer, breach, changed_by=changed_by)
            for breach in breaches
        ]
        open_flags = [flag for flag in flags if flag is not None]

        if any(breach.rule.action == TransferAmlRule.Action.HOLD for breach in breaches):
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
        elif transfer.compliance_status == Transfer.ComplianceStatus.CLEAR:
            transfer.compliance_status = Transfer.ComplianceStatus.FLAGGED

        transfer.save(update_fields=("compliance_status", "updated_at"))
        return open_flags


def evaluate_recipient_verification_rules(
    transfer: Transfer,
    *,
    changed_by=None,
) -> list[TransferComplianceFlag]:
    breaches = [
        breach
        for rule in get_matching_recipient_verification_rules(transfer)
        if (breach := evaluate_recipient_verification_rule(rule, transfer)) is not None
    ]

    if not breaches:
        return []

    with transaction.atomic():
        flags = [
            create_recipient_verification_flag(
                transfer,
                breach,
                changed_by=changed_by,
            )
            for breach in breaches
        ]
        open_flags = [flag for flag in flags if flag is not None]

        if any(
            breach.rule.action == RecipientVerificationRule.Action.HOLD
            for breach in breaches
        ):
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
        elif transfer.compliance_status == Transfer.ComplianceStatus.CLEAR:
            transfer.compliance_status = Transfer.ComplianceStatus.FLAGGED

        transfer.save(update_fields=("compliance_status", "updated_at"))
        return open_flags


def get_matching_limit_rules(transfer: Transfer):
    corridor = get_transfer_corridor(transfer)
    queryset = TransferLimitRule.objects.filter(is_active=True)
    queryset = queryset.filter(Q(sender__isnull=True) | Q(sender=transfer.sender))
    queryset = queryset.filter(
        Q(source_currency__isnull=True)
        | Q(source_currency=transfer.source_currency),
    )
    queryset = queryset.filter(
        Q(payout_method="")
        | Q(payout_method=transfer.payout_method),
    )

    if corridor:
        queryset = queryset.filter(Q(corridor__isnull=True) | Q(corridor=corridor))
    else:
        queryset = queryset.filter(corridor__isnull=True)

    return queryset


def get_matching_risk_rules(transfer: Transfer):
    corridor = get_transfer_corridor(transfer)
    queryset = TransferRiskRule.objects.filter(is_active=True)
    queryset = queryset.filter(Q(sender__isnull=True) | Q(sender=transfer.sender))
    queryset = queryset.filter(
        Q(source_currency__isnull=True)
        | Q(source_currency=transfer.source_currency),
    )
    queryset = queryset.filter(
        Q(destination_country__isnull=True)
        | Q(destination_country=transfer.destination_country),
    )
    queryset = queryset.filter(
        Q(payout_method="")
        | Q(payout_method=transfer.payout_method),
    )

    if corridor:
        queryset = queryset.filter(Q(corridor__isnull=True) | Q(corridor=corridor))
    else:
        queryset = queryset.filter(corridor__isnull=True)

    return queryset


def get_matching_aml_rules(transfer: Transfer):
    corridor = get_transfer_corridor(transfer)
    queryset = TransferAmlRule.objects.filter(is_active=True)
    queryset = queryset.filter(Q(sender__isnull=True) | Q(sender=transfer.sender))
    queryset = queryset.filter(
        Q(source_currency__isnull=True)
        | Q(source_currency=transfer.source_currency),
    )
    queryset = queryset.filter(
        Q(destination_country__isnull=True)
        | Q(destination_country=transfer.destination_country),
    )
    queryset = queryset.filter(
        Q(payout_method="")
        | Q(payout_method=transfer.payout_method),
    )

    if corridor:
        queryset = queryset.filter(Q(corridor__isnull=True) | Q(corridor=corridor))
    else:
        queryset = queryset.filter(corridor__isnull=True)

    return queryset


def get_matching_recipient_verification_rules(transfer: Transfer):
    corridor = get_transfer_corridor(transfer)
    queryset = RecipientVerificationRule.objects.filter(is_active=True)
    queryset = queryset.filter(
        Q(source_currency__isnull=True)
        | Q(source_currency=transfer.source_currency),
    )
    queryset = queryset.filter(
        Q(destination_country__isnull=True)
        | Q(destination_country=transfer.destination_country),
    )
    queryset = queryset.filter(
        Q(payout_method="")
        | Q(payout_method=transfer.payout_method),
    )
    queryset = queryset.filter(
        Q(min_send_amount__isnull=True)
        | Q(min_send_amount__lte=transfer.send_amount),
    )

    if corridor:
        queryset = queryset.filter(Q(corridor__isnull=True) | Q(corridor=corridor))
    else:
        queryset = queryset.filter(corridor__isnull=True)

    return queryset


def ensure_transfer_sanctions_checks(
    transfer: Transfer,
    *,
    changed_by=None,
) -> list[TransferSanctionsCheck]:
    provider = get_sanctions_aml_provider()
    checks = []
    for party_type in (
        TransferSanctionsCheck.PartyType.SENDER,
        TransferSanctionsCheck.PartyType.RECIPIENT,
    ):
        screened_name, payload = build_sanctions_screening_payload(transfer, party_type)
        existing_check = TransferSanctionsCheck.objects.filter(
            transfer=transfer,
            party_type=party_type,
        ).first()
        if existing_check:
            checks.append(existing_check)
            continue

        result = provider.screen_party(
            party_type=party_type,
            screened_name=screened_name,
            payload=payload,
            transfer_reference=transfer.reference,
        )
        check = TransferSanctionsCheck.objects.create(
            transfer=transfer,
            party_type=party_type,
            status=result.status,
            screened_name=screened_name,
            provider_name=result.provider_name,
            provider_reference=result.provider_reference,
            screening_payload=result.screening_payload,
            response_payload=result.response_payload,
            match_score=result.match_score,
            review_note=result.status_reason,
        )
        apply_provider_sanctions_result(check, changed_by=changed_by)
        checks.append(check)

    return checks


def apply_provider_sanctions_result(
    check: TransferSanctionsCheck,
    *,
    changed_by=None,
) -> None:
    transfer = check.transfer
    previous_compliance_status = transfer.compliance_status
    if check.status in {
        TransferSanctionsCheck.Status.POSSIBLE_MATCH,
        TransferSanctionsCheck.Status.CONFIRMED_MATCH,
    }:
        create_sanctions_flag(check, changed_by=changed_by)
        if transfer.compliance_status != Transfer.ComplianceStatus.ON_HOLD:
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
            transfer.save(update_fields=("compliance_status", "updated_at"))

    if check.status in {
        TransferSanctionsCheck.Status.CLEAR,
        TransferSanctionsCheck.Status.SKIPPED,
    }:
        resolve_sanctions_flag(check, changed_by=changed_by)

    if check.status != TransferSanctionsCheck.Status.QUEUED:
        record_compliance_event(
            transfer,
            TransferComplianceEvent.Action.SCREENING,
            changed_by=changed_by,
            note=check.review_note,
            previous_transfer_status=transfer.status,
            previous_compliance_status=previous_compliance_status,
            metadata={
                "party_type": check.party_type,
                "screening_status": check.status,
                "provider_name": check.provider_name,
                "provider_reference": check.provider_reference,
            },
        )


def evaluate_limit_rule(
    rule: TransferLimitRule,
    transfer: Transfer,
) -> LimitBreach | None:
    observed_amount = get_observed_amount(rule, transfer)
    if observed_amount > rule.max_send_amount:
        return LimitBreach(rule=rule, observed_amount=observed_amount)
    return None


def evaluate_recipient_verification_rule(
    rule: RecipientVerificationRule,
    transfer: Transfer,
) -> RecipientVerificationBreach | None:
    recipient_status = transfer.recipient.verification_status
    if recipient_status != Recipient.VerificationStatus.VERIFIED:
        return RecipientVerificationBreach(
            rule=rule,
            recipient_status=recipient_status,
        )
    return None


def build_sanctions_screening_payload(
    transfer: Transfer,
    party_type: str,
) -> tuple[str, dict]:
    if party_type == TransferSanctionsCheck.PartyType.SENDER:
        profile = get_sender_profile(transfer)
        screened_name = f"{transfer.sender.first_name} {transfer.sender.last_name}".strip()
        if not screened_name:
            screened_name = transfer.sender.email
        return screened_name, {
            "party_type": party_type,
            "name": screened_name,
            "email": transfer.sender.email,
            "phone_number": profile.phone_number if profile else "",
            "country": profile.country.iso_code if profile and profile.country_id else "",
        }

    recipient = transfer.recipient
    screened_name = recipient.full_name
    return screened_name, {
        "party_type": party_type,
        "name": screened_name,
        "phone_number": recipient.phone_number,
        "country": recipient.country.iso_code,
        "payout_method": transfer.payout_method,
    }


def evaluate_aml_rule(
    rule: TransferAmlRule,
    transfer: Transfer,
) -> AmlRuleBreach | None:
    if rule.rule_type == TransferAmlRule.RuleType.LARGE_TRANSFER:
        if rule.threshold_amount is None:
            return None

        if transfer.send_amount > rule.threshold_amount:
            return AmlRuleBreach(
                rule=rule,
                observed_value=str(transfer.send_amount),
                details={
                    "threshold_amount": str(rule.threshold_amount),
                    "observed_amount": str(transfer.send_amount),
                },
            )

    activity_queryset = get_aml_activity_queryset(rule, transfer)

    if rule.rule_type == TransferAmlRule.RuleType.DAILY_VOLUME:
        if rule.threshold_amount is None:
            return None

        start_at = get_period_start(TransferLimitRule.Period.DAILY, transfer.created_at)
        observed_amount = (
            activity_queryset.filter(
                created_at__gte=start_at,
                created_at__lte=timezone.now(),
            ).aggregate(total=Sum("send_amount"))["total"]
            or Decimal("0.00")
        )
        if observed_amount > rule.threshold_amount:
            return AmlRuleBreach(
                rule=rule,
                observed_value=str(observed_amount),
                details={
                    "threshold_amount": str(rule.threshold_amount),
                    "observed_amount": str(observed_amount),
                    "period": "daily",
                },
            )

    if rule.rule_type == TransferAmlRule.RuleType.VELOCITY_COUNT:
        if not rule.transfer_count or not rule.window_minutes:
            return None

        start_at = transfer.created_at - timedelta(minutes=rule.window_minutes)
        observed_count = activity_queryset.filter(
            created_at__gte=start_at,
            created_at__lte=timezone.now(),
        ).count()
        if observed_count >= rule.transfer_count:
            return AmlRuleBreach(
                rule=rule,
                observed_value=str(observed_count),
                details={
                    "transfer_count": str(rule.transfer_count),
                    "observed_count": str(observed_count),
                    "window_minutes": str(rule.window_minutes),
                },
            )

    if rule.rule_type == TransferAmlRule.RuleType.VELOCITY_VOLUME:
        if rule.threshold_amount is None or not rule.window_minutes:
            return None

        start_at = transfer.created_at - timedelta(minutes=rule.window_minutes)
        observed_amount = (
            activity_queryset.filter(
                created_at__gte=start_at,
                created_at__lte=timezone.now(),
            ).aggregate(total=Sum("send_amount"))["total"]
            or Decimal("0.00")
        )
        if observed_amount > rule.threshold_amount:
            return AmlRuleBreach(
                rule=rule,
                observed_value=str(observed_amount),
                details={
                    "threshold_amount": str(rule.threshold_amount),
                    "observed_amount": str(observed_amount),
                    "window_minutes": str(rule.window_minutes),
                },
            )

    return None


def evaluate_risk_rule(
    rule: TransferRiskRule,
    transfer: Transfer,
) -> RiskRuleBreach | None:
    if rule.rule_type == TransferRiskRule.RuleType.HIGH_AMOUNT:
        if rule.threshold_amount is None:
            return None
        if transfer.send_amount > rule.threshold_amount:
            return RiskRuleBreach(
                rule=rule,
                observed_value=str(transfer.send_amount),
                details={
                    "threshold_amount": str(rule.threshold_amount),
                    "observed_amount": str(transfer.send_amount),
                },
            )

    if rule.rule_type == TransferRiskRule.RuleType.FIRST_TRANSFER:
        has_previous_transfer = (
            Transfer.objects.filter(sender=transfer.sender)
            .exclude(id=transfer.id)
            .exclude(status__in=FINAL_TRANSFER_STATUSES)
            .exists()
        )
        if not has_previous_transfer:
            return RiskRuleBreach(
                rule=rule,
                observed_value="first_transfer",
                details={"previous_transfer_count": "0"},
            )

    if rule.rule_type == TransferRiskRule.RuleType.RAPID_REPEAT:
        if not rule.repeat_count or not rule.window_minutes:
            return None

        start_at = transfer.created_at - timedelta(minutes=rule.window_minutes)
        observed_count = (
            Transfer.objects.filter(
                sender=transfer.sender,
                created_at__gte=start_at,
                created_at__lte=timezone.now(),
            )
            .exclude(status__in=FINAL_TRANSFER_STATUSES)
            .count()
        )
        if observed_count >= rule.repeat_count:
            return RiskRuleBreach(
                rule=rule,
                observed_value=str(observed_count),
                details={
                    "observed_count": str(observed_count),
                    "repeat_count": str(rule.repeat_count),
                    "window_minutes": str(rule.window_minutes),
                },
            )

    if rule.rule_type == TransferRiskRule.RuleType.INCOMPLETE_PROFILE:
        if not is_sender_profile_complete(transfer):
            return RiskRuleBreach(
                rule=rule,
                observed_value="incomplete_profile",
                details=get_sender_profile_details(transfer),
            )

    if rule.rule_type == TransferRiskRule.RuleType.UNVERIFIED_KYC:
        kyc_status = get_sender_kyc_status(transfer)
        if kyc_status != SenderProfile.KycStatus.VERIFIED:
            return RiskRuleBreach(
                rule=rule,
                observed_value=kyc_status,
                details={"kyc_status": kyc_status},
            )

    if rule.rule_type == TransferRiskRule.RuleType.DESTINATION_METHOD:
        return RiskRuleBreach(
            rule=rule,
            observed_value=(
                f"{transfer.destination_country.iso_code}:"
                f"{transfer.payout_method}"
            ),
            details={
                "destination_country": transfer.destination_country.iso_code,
                "payout_method": transfer.payout_method,
            },
        )

    return None


def get_aml_activity_queryset(rule: TransferAmlRule, transfer: Transfer):
    queryset = Transfer.objects.filter(sender=transfer.sender).exclude(
        status__in=FINAL_TRANSFER_STATUSES,
    )

    if rule.source_currency_id:
        queryset = queryset.filter(source_currency=transfer.source_currency)

    if rule.destination_country_id:
        queryset = queryset.filter(destination_country=transfer.destination_country)

    if rule.payout_method:
        queryset = queryset.filter(payout_method=transfer.payout_method)

    if rule.corridor_id:
        queryset = queryset.filter(
            source_country=rule.corridor.source_country,
            destination_country=rule.corridor.destination_country,
        )

    return queryset


def get_observed_amount(rule: TransferLimitRule, transfer: Transfer) -> Decimal:
    if rule.period == TransferLimitRule.Period.PER_TRANSFER:
        return transfer.send_amount

    start_at = get_period_start(rule.period, transfer.created_at)
    queryset = Transfer.objects.filter(
        sender=transfer.sender,
        source_currency=transfer.source_currency,
        created_at__gte=start_at,
        created_at__lte=timezone.now(),
    ).exclude(status__in=FINAL_TRANSFER_STATUSES)

    corridor = rule.corridor or get_transfer_corridor(transfer)
    if rule.corridor and corridor:
        queryset = queryset.filter(
            source_country=corridor.source_country,
            destination_country=corridor.destination_country,
        )

    if rule.payout_method:
        queryset = queryset.filter(payout_method=rule.payout_method)

    return queryset.aggregate(total=Sum("send_amount"))["total"] or Decimal("0.00")


def get_period_start(period: str, reference_time):
    if period == TransferLimitRule.Period.DAILY:
        return reference_time.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == TransferLimitRule.Period.MONTHLY:
        return reference_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return reference_time


def get_transfer_corridor(transfer: Transfer):
    return (
        CountryCorridor.objects.filter(
            source_country=transfer.source_country,
            destination_country=transfer.destination_country,
            source_currency=transfer.source_currency,
            destination_currency=transfer.destination_currency,
        )
        .order_by("-is_active", "-created_at")
        .first()
    )


def get_sender_profile(transfer: Transfer) -> SenderProfile | None:
    try:
        return transfer.sender.sender_profile
    except SenderProfile.DoesNotExist:
        return None


def get_sender_profile_details(transfer: Transfer) -> dict:
    profile = get_sender_profile(transfer)
    return {
        "has_first_name": bool(transfer.sender.first_name),
        "has_last_name": bool(transfer.sender.last_name),
        "has_profile": bool(profile),
        "has_phone_number": bool(profile and profile.phone_number),
        "has_sender_country": bool(profile and profile.country_id),
    }


def is_sender_profile_complete(transfer: Transfer) -> bool:
    details = get_sender_profile_details(transfer)
    return all(details.values())


def get_sender_kyc_status(transfer: Transfer) -> str:
    profile = get_sender_profile(transfer)
    if not profile:
        return SenderProfile.KycStatus.NOT_STARTED
    return profile.kyc_status


def create_limit_flag(
    transfer: Transfer,
    breach: LimitBreach,
    *,
    changed_by=None,
) -> TransferComplianceFlag | None:
    rule = breach.rule
    existing_flag = transfer.compliance_flags.filter(
        code=rule.code,
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).first()

    if existing_flag:
        return existing_flag

    return TransferComplianceFlag.objects.create(
        transfer=transfer,
        category=TransferComplianceFlag.Category.LIMIT,
        severity=rule.severity,
        code=rule.code,
        title=f"Transfer limit exceeded: {rule.name}",
        description=rule.description
        or (
            f"Observed send amount {breach.observed_amount} exceeds "
            f"configured {rule.period} limit {rule.max_send_amount}."
        ),
        metadata={
            "rule_id": str(rule.id),
            "period": rule.period,
            "action": rule.action,
            "max_send_amount": str(rule.max_send_amount),
            "observed_amount": str(breach.observed_amount),
        },
        created_by=changed_by,
    )


def create_risk_rule_flag(
    transfer: Transfer,
    breach: RiskRuleBreach,
    *,
    changed_by=None,
) -> TransferComplianceFlag | None:
    rule = breach.rule
    existing_flag = transfer.compliance_flags.filter(
        code=rule.code,
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).first()

    if existing_flag:
        return existing_flag

    return TransferComplianceFlag.objects.create(
        transfer=transfer,
        category=TransferComplianceFlag.Category.RISK_RULE,
        severity=rule.severity,
        code=rule.code,
        title=f"Risk rule triggered: {rule.name}",
        description=rule.description
        or f"Configured {rule.get_rule_type_display()} rule triggered.",
        metadata={
            "rule_id": str(rule.id),
            "rule_type": rule.rule_type,
            "action": rule.action,
            "observed_value": breach.observed_value,
            **breach.details,
        },
        created_by=changed_by,
    )


def create_recipient_verification_flag(
    transfer: Transfer,
    breach: RecipientVerificationBreach,
    *,
    changed_by=None,
) -> TransferComplianceFlag | None:
    rule = breach.rule
    existing_flag = transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.RECIPIENT,
        code=rule.code,
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).first()

    if existing_flag:
        return existing_flag

    return TransferComplianceFlag.objects.create(
        transfer=transfer,
        category=TransferComplianceFlag.Category.RECIPIENT,
        severity=rule.severity,
        code=rule.code,
        title=f"Recipient verification required: {rule.name}",
        description=rule.description
        or (
            "Recipient verification status must be cleared before this transfer "
            "can proceed."
        ),
        metadata={
            "rule_id": str(rule.id),
            "action": rule.action,
            "recipient_id": str(transfer.recipient_id),
            "recipient_verification_status": breach.recipient_status,
            "min_send_amount": (
                str(rule.min_send_amount) if rule.min_send_amount is not None else ""
            ),
        },
        created_by=changed_by,
    )


def create_aml_flag(
    transfer: Transfer,
    breach: AmlRuleBreach,
    *,
    changed_by=None,
) -> TransferComplianceFlag | None:
    rule = breach.rule
    metadata = {
        "rule_id": str(rule.id),
        "rule_type": rule.rule_type,
        "action": rule.action,
        "observed_value": breach.observed_value,
        "aml_workflow_status": "open",
        **breach.details,
    }
    existing_flag = transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.AML,
        code=rule.code,
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).first()

    if existing_flag:
        existing_flag.severity = rule.severity
        existing_flag.title = f"AML monitoring triggered: {rule.name}"
        existing_flag.description = rule.description or (
            f"Configured {rule.get_rule_type_display()} AML rule triggered."
        )
        existing_flag.metadata = {
            **existing_flag.metadata,
            **metadata,
        }
        existing_flag.save(
            update_fields=("severity", "title", "description", "metadata", "updated_at"),
        )
        return existing_flag

    return TransferComplianceFlag.objects.create(
        transfer=transfer,
        category=TransferComplianceFlag.Category.AML,
        severity=rule.severity,
        code=rule.code,
        title=f"AML monitoring triggered: {rule.name}",
        description=rule.description
        or f"Configured {rule.get_rule_type_display()} AML rule triggered.",
        metadata=metadata,
        created_by=changed_by,
    )


def get_sanctions_flag_code(check: TransferSanctionsCheck) -> str:
    return f"SANCTIONS_{check.party_type.upper()}_SCREENING"


def create_sanctions_flag(
    check: TransferSanctionsCheck,
    *,
    changed_by=None,
) -> TransferComplianceFlag | None:
    code = get_sanctions_flag_code(check)
    existing_flag = check.transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.SANCTIONS,
        code=code,
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).first()

    severity = (
        TransferComplianceFlag.Severity.CRITICAL
        if check.status == TransferSanctionsCheck.Status.CONFIRMED_MATCH
        else TransferComplianceFlag.Severity.HIGH
    )

    if existing_flag:
        if existing_flag.severity != severity or existing_flag.description != check.review_note:
            existing_flag.severity = severity
            existing_flag.description = check.review_note or existing_flag.description
            existing_flag.metadata = {
                **existing_flag.metadata,
                "screening_status": check.status,
                "provider_reference": check.provider_reference,
            }
            existing_flag.save(
                update_fields=("severity", "description", "metadata", "updated_at"),
            )
        return existing_flag

    return TransferComplianceFlag.objects.create(
        transfer=check.transfer,
        category=TransferComplianceFlag.Category.SANCTIONS,
        severity=severity,
        code=code,
        title=f"Sanctions screening match: {check.get_party_type_display()}",
        description=check.review_note
        or (
            f"{check.get_party_type_display()} screening returned "
            f"{check.get_status_display().lower()}."
        ),
        metadata={
            "party_type": check.party_type,
            "screening_status": check.status,
            "provider_name": check.provider_name,
            "provider_reference": check.provider_reference,
        },
        created_by=changed_by,
    )


def resolve_sanctions_flag(
    check: TransferSanctionsCheck,
    *,
    changed_by=None,
) -> None:
    check.transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.SANCTIONS,
        code=get_sanctions_flag_code(check),
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).update(
        status=TransferComplianceFlag.Status.RESOLVED,
        resolved_by=changed_by,
        resolved_at=timezone.now(),
        updated_at=timezone.now(),
    )


def review_transfer_sanctions_check(
    check: TransferSanctionsCheck,
    *,
    status: str,
    reviewed_by=None,
    review_note: str = "",
    provider_reference: str = "",
    match_score=None,
) -> Transfer:
    transfer = check.transfer
    previous_compliance_status = transfer.compliance_status
    previous_status = check.status

    check.status = status
    check.review_note = review_note
    check.provider_reference = provider_reference or check.provider_reference
    check.match_score = match_score
    check.reviewed_by = reviewed_by
    check.reviewed_at = timezone.now()
    check.save(
        update_fields=(
            "status",
            "review_note",
            "provider_reference",
            "match_score",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ),
    )

    if status in {
        TransferSanctionsCheck.Status.POSSIBLE_MATCH,
        TransferSanctionsCheck.Status.CONFIRMED_MATCH,
    }:
        create_sanctions_flag(check, changed_by=reviewed_by)
        if transfer.compliance_status != Transfer.ComplianceStatus.ON_HOLD:
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
            transfer.save(update_fields=("compliance_status", "updated_at"))

    if status in {
        TransferSanctionsCheck.Status.CLEAR,
        TransferSanctionsCheck.Status.SKIPPED,
    }:
        resolve_sanctions_flag(check, changed_by=reviewed_by)

    record_compliance_event(
        transfer,
        TransferComplianceEvent.Action.SCREENING,
        changed_by=reviewed_by,
        note=review_note,
        previous_transfer_status=transfer.status,
        previous_compliance_status=previous_compliance_status,
        metadata={
            "party_type": check.party_type,
            "previous_screening_status": previous_status,
            "screening_status": status,
            "provider_reference": check.provider_reference,
        },
    )
    return transfer


def create_manual_hold_flag(
    transfer: Transfer,
    *,
    changed_by=None,
    note: str = "",
) -> TransferComplianceFlag:
    existing_flag = transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.MANUAL,
        code="MANUAL_HOLD",
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).first()

    if existing_flag:
        if note and existing_flag.description != note:
            existing_flag.description = note
            existing_flag.save(update_fields=("description", "updated_at"))
        return existing_flag

    return TransferComplianceFlag.objects.create(
        transfer=transfer,
        category=TransferComplianceFlag.Category.MANUAL,
        severity=TransferComplianceFlag.Severity.HIGH,
        code="MANUAL_HOLD",
        title="Manual compliance hold",
        description=note or "Transfer placed on manual compliance hold.",
        metadata={"source": "staff_action"},
        created_by=changed_by,
    )


def apply_compliance_action(
    transfer: Transfer,
    action: str,
    *,
    performed_by=None,
    note: str = "",
) -> Transfer:
    if action == TransferComplianceEvent.Action.NOTE:
        record_compliance_event(
            transfer,
            TransferComplianceEvent.Action.NOTE,
            changed_by=performed_by,
            note=note,
            previous_transfer_status=transfer.status,
            previous_compliance_status=transfer.compliance_status,
        )
        return transfer

    if action == TransferComplianceEvent.Action.HOLD:
        return apply_compliance_hold(
            transfer,
            performed_by=performed_by,
            note=note,
        )

    if action == TransferComplianceEvent.Action.REVIEW:
        return apply_compliance_review(
            transfer,
            performed_by=performed_by,
            note=note,
        )

    if action == TransferComplianceEvent.Action.APPROVE:
        if transfer.status != Transfer.Status.UNDER_REVIEW:
            raise serializers.ValidationError(
                {
                    "action": (
                        "Transfer must be under review before compliance approval."
                    ),
                },
            )

        return transition_transfer_status(
            transfer,
            Transfer.Status.APPROVED,
            changed_by=performed_by,
            note=note,
        )

    if action == TransferComplianceEvent.Action.REJECT:
        if transfer.status != Transfer.Status.UNDER_REVIEW:
            raise serializers.ValidationError(
                {
                    "action": (
                        "Transfer must be under review before compliance rejection."
                    ),
                },
            )

        return transition_transfer_status(
            transfer,
            Transfer.Status.REJECTED,
            changed_by=performed_by,
            note=note,
        )

    raise serializers.ValidationError({"action": "Unsupported compliance action."})


def review_transfer_aml_flag(
    flag: TransferComplianceFlag,
    *,
    decision: str,
    reviewed_by=None,
    review_note: str = "",
    escalation_destination: str = "",
    escalation_reference: str = "",
) -> Transfer:
    if flag.category != TransferComplianceFlag.Category.AML:
        raise serializers.ValidationError({"flag_id": "AML flag not found."})

    transfer = flag.transfer
    previous_compliance_status = transfer.compliance_status
    previous_flag_status = flag.status
    now = timezone.now()
    metadata = {**flag.metadata}

    aml_workflow_status = {
        "acknowledge": "acknowledged",
        "review": "under_review",
        "escalate": "escalated",
        "clear": "cleared",
        "dismiss": "dismissed",
        "report": "reported",
    }[decision]

    if decision in {"acknowledge", "review", "escalate", "report"}:
        flag.status = TransferComplianceFlag.Status.ACKNOWLEDGED

    if decision == "clear":
        flag.status = TransferComplianceFlag.Status.RESOLVED
        flag.resolved_by = reviewed_by
        flag.resolved_at = now

    if decision == "dismiss":
        flag.status = TransferComplianceFlag.Status.DISMISSED
        flag.resolved_by = reviewed_by
        flag.resolved_at = now

    metadata.update(
        {
            "aml_workflow_status": aml_workflow_status,
            "aml_decision": decision,
            "review_note": review_note,
            "reviewed_at": now.isoformat(),
            "reviewed_by_email": getattr(reviewed_by, "email", ""),
        },
    )
    if escalation_destination:
        metadata["escalation_destination"] = escalation_destination
    if escalation_reference:
        metadata["escalation_reference"] = escalation_reference

    flag.metadata = metadata
    update_fields = ("status", "metadata", "updated_at")
    if flag.status in {
        TransferComplianceFlag.Status.RESOLVED,
        TransferComplianceFlag.Status.DISMISSED,
    }:
        update_fields = (
            "status",
            "metadata",
            "resolved_by",
            "resolved_at",
            "updated_at",
        )
    flag.save(update_fields=update_fields)

    if decision in {"review", "escalate", "report"}:
        if transfer.compliance_status != Transfer.ComplianceStatus.ON_HOLD:
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
            transfer.save(update_fields=("compliance_status", "updated_at"))
    elif decision in {"clear", "dismiss"}:
        sync_transfer_compliance_status_from_flags(transfer)

    record_compliance_event(
        transfer,
        TransferComplianceEvent.Action.AML,
        changed_by=reviewed_by,
        note=review_note,
        previous_transfer_status=transfer.status,
        previous_compliance_status=previous_compliance_status,
        metadata={
            "flag_id": str(flag.id),
            "flag_code": flag.code,
            "previous_flag_status": previous_flag_status,
            "flag_status": flag.status,
            "aml_decision": decision,
            "escalation_destination": escalation_destination,
            "escalation_reference": escalation_reference,
        },
    )
    return transfer


def sync_transfer_compliance_status_from_flags(transfer: Transfer) -> None:
    open_flags = list(
        transfer.compliance_flags.filter(
            status__in=(
                TransferComplianceFlag.Status.OPEN,
                TransferComplianceFlag.Status.ACKNOWLEDGED,
            ),
        ),
    )

    if any(is_blocking_flag(flag) for flag in open_flags):
        next_status = Transfer.ComplianceStatus.ON_HOLD
    elif open_flags:
        next_status = Transfer.ComplianceStatus.FLAGGED
    elif transfer.status == Transfer.Status.UNDER_REVIEW:
        next_status = Transfer.ComplianceStatus.UNDER_REVIEW
    elif transfer.status in {
        Transfer.Status.APPROVED,
        Transfer.Status.PROCESSING_PAYOUT,
        Transfer.Status.PAID_OUT,
        Transfer.Status.COMPLETED,
    }:
        next_status = Transfer.ComplianceStatus.APPROVED
    elif transfer.status == Transfer.Status.REJECTED:
        next_status = Transfer.ComplianceStatus.REJECTED
    else:
        next_status = Transfer.ComplianceStatus.CLEAR

    if transfer.compliance_status != next_status:
        transfer.compliance_status = next_status
        transfer.save(update_fields=("compliance_status", "updated_at"))


def is_blocking_flag(flag: TransferComplianceFlag) -> bool:
    if flag.category in {
        TransferComplianceFlag.Category.MANUAL,
        TransferComplianceFlag.Category.SANCTIONS,
        TransferComplianceFlag.Category.AML,
    }:
        return True

    return flag.metadata.get("action") == "hold"


def apply_compliance_hold(
    transfer: Transfer,
    *,
    performed_by=None,
    note: str = "",
) -> Transfer:
    if transfer.status not in {
        Transfer.Status.FUNDING_RECEIVED,
        Transfer.Status.UNDER_REVIEW,
    }:
        raise serializers.ValidationError(
            {
                "action": (
                    "Manual hold is only available after funding and before payout."
                ),
            },
        )

    if transfer.compliance_status == Transfer.ComplianceStatus.ON_HOLD:
        raise serializers.ValidationError(
            {"action": "Transfer is already on manual compliance hold."},
        )

    previous_transfer_status = transfer.status
    previous_compliance_status = transfer.compliance_status
    transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
    transfer.save(update_fields=("compliance_status", "updated_at"))
    create_manual_hold_flag(transfer, changed_by=performed_by, note=note)
    record_compliance_event(
        transfer,
        TransferComplianceEvent.Action.HOLD,
        changed_by=performed_by,
        note=note,
        previous_transfer_status=previous_transfer_status,
        previous_compliance_status=previous_compliance_status,
    )
    return transfer


def apply_compliance_review(
    transfer: Transfer,
    *,
    performed_by=None,
    note: str = "",
) -> Transfer:
    if transfer.status == Transfer.Status.FUNDING_RECEIVED:
        return transition_transfer_status(
            transfer,
            Transfer.Status.UNDER_REVIEW,
            changed_by=performed_by,
            note=note,
        )

    if transfer.status != Transfer.Status.UNDER_REVIEW:
        raise serializers.ValidationError(
            {"action": "Transfer must be funded before compliance review starts."},
        )

    if transfer.compliance_status == Transfer.ComplianceStatus.UNDER_REVIEW:
        raise serializers.ValidationError(
            {"action": "Transfer is already under compliance review."},
        )

    previous_transfer_status = transfer.status
    previous_compliance_status = transfer.compliance_status
    transfer.compliance_status = Transfer.ComplianceStatus.UNDER_REVIEW
    transfer.save(update_fields=("compliance_status", "updated_at"))
    transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.MANUAL,
        code="MANUAL_HOLD",
        status=TransferComplianceFlag.Status.OPEN,
    ).update(
        status=TransferComplianceFlag.Status.ACKNOWLEDGED,
        updated_at=transfer.updated_at,
    )
    record_compliance_event(
        transfer,
        TransferComplianceEvent.Action.REVIEW,
        changed_by=performed_by,
        note=note,
        previous_transfer_status=previous_transfer_status,
        previous_compliance_status=previous_compliance_status,
    )
    return transfer
