from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.security import decrypt_text

from .models import (
    Transfer,
    TransferComplianceFlag,
    TransferPaymentFraudRule,
    TransferPaymentInstruction,
)
from .services import apply_payment_instruction_status


@dataclass(frozen=True)
class PaymentFraudBreach:
    rule: TransferPaymentFraudRule
    observed_value: str
    details: dict


def evaluate_payment_fraud_rules(
    instruction: TransferPaymentInstruction,
    *,
    changed_by=None,
) -> list[TransferComplianceFlag]:
    breaches = [
        breach
        for rule in get_matching_payment_fraud_rules(instruction)
        if (breach := evaluate_payment_fraud_rule(rule, instruction)) is not None
    ]

    if not breaches:
        return []

    transfer = instruction.transfer
    previous_status = instruction.status

    with transaction.atomic():
        flags = [
            create_payment_fraud_flag(instruction, breach, changed_by=changed_by)
            for breach in breaches
        ]
        open_flags = [flag for flag in flags if flag is not None]
        has_hold = any(
            breach.rule.action == TransferPaymentFraudRule.Action.HOLD
            for breach in breaches
        )

        if has_hold:
            transfer.compliance_status = Transfer.ComplianceStatus.ON_HOLD
        elif transfer.compliance_status == Transfer.ComplianceStatus.CLEAR:
            transfer.compliance_status = Transfer.ComplianceStatus.FLAGGED

        transfer.save(update_fields=("compliance_status", "updated_at"))

        if has_hold and previous_status in {
            TransferPaymentInstruction.Status.NOT_STARTED,
            TransferPaymentInstruction.Status.PENDING_AUTHORIZATION,
            TransferPaymentInstruction.Status.AUTHORIZED,
        }:
            apply_payment_instruction_status(
                instruction,
                TransferPaymentInstruction.Status.REQUIRES_REVIEW,
                changed_by=changed_by,
                note="Payment fraud rule requires review.",
                status_reason="Payment requires review before funding can continue.",
                instruction_updates={
                    "payment_fraud_hold": True,
                    "payment_fraud_rule_codes": [
                        breach.rule.code
                        for breach in breaches
                        if breach.rule.action == TransferPaymentFraudRule.Action.HOLD
                    ],
                },
            )

        return open_flags


def get_matching_payment_fraud_rules(
    instruction: TransferPaymentInstruction,
):
    transfer = instruction.transfer
    return TransferPaymentFraudRule.objects.filter(is_active=True).filter(
        Q(sender__isnull=True) | Q(sender=transfer.sender),
        Q(source_currency__isnull=True) | Q(source_currency=transfer.source_currency),
        Q(destination_country__isnull=True)
        | Q(destination_country=transfer.destination_country),
        Q(payout_method="") | Q(payout_method=transfer.payout_method),
        Q(payment_method="") | Q(payment_method=instruction.payment_method),
    )


def evaluate_payment_fraud_rule(
    rule: TransferPaymentFraudRule,
    instruction: TransferPaymentInstruction,
) -> PaymentFraudBreach | None:
    if rule.rule_type == TransferPaymentFraudRule.RuleType.UNUSUAL_AMOUNT:
        if rule.threshold_amount is None or instruction.amount < rule.threshold_amount:
            return None

        return PaymentFraudBreach(
            rule=rule,
            observed_value=str(instruction.amount),
            details={
                "threshold_amount": str(rule.threshold_amount),
                "payment_amount": str(instruction.amount),
                "currency": instruction.currency.code,
            },
        )

    if rule.rule_type == TransferPaymentFraudRule.RuleType.REPEATED_ATTEMPTS:
        attempt_count = rule.attempt_count or 2
        window_minutes = rule.window_minutes or 60
        since = timezone.now() - timedelta(minutes=window_minutes)
        attempts = TransferPaymentInstruction.objects.filter(
            transfer__sender=instruction.transfer.sender,
            payment_method=instruction.payment_method,
            created_at__gte=since,
            status__in=(
                TransferPaymentInstruction.Status.FAILED,
                TransferPaymentInstruction.Status.REQUIRES_REVIEW,
            ),
        ).count()

        if attempts < attempt_count:
            return None

        return PaymentFraudBreach(
            rule=rule,
            observed_value=str(attempts),
            details={
                "attempt_count": str(attempts),
                "threshold_count": str(attempt_count),
                "window_minutes": str(window_minutes),
                "payment_method": instruction.payment_method,
            },
        )

    if rule.rule_type == TransferPaymentFraudRule.RuleType.CARDHOLDER_NAME_MISMATCH:
        cardholder_name = ""
        encrypted_cardholder_name = instruction.instructions.get(
            "authorization_cardholder_name_encrypted",
            "",
        )
        if encrypted_cardholder_name:
            cardholder_name = decrypt_text(str(encrypted_cardholder_name))
        else:
            cardholder_name = str(
                instruction.instructions.get("authorization_cardholder_name", ""),
            )
        sender_name = (
            f"{instruction.transfer.sender.first_name} "
            f"{instruction.transfer.sender.last_name}"
        )
        if not cardholder_name.strip() or not sender_name.strip():
            return None

        if normalize_name(cardholder_name) == normalize_name(sender_name):
            return None

        return PaymentFraudBreach(
            rule=rule,
            observed_value=cardholder_name,
            details={
                "cardholder_name": cardholder_name,
                "sender_name": sender_name.strip(),
                "payment_method": instruction.payment_method,
            },
        )

    if rule.rule_type == TransferPaymentFraudRule.RuleType.COMPLIANCE_HOLD:
        if instruction.transfer.compliance_status not in {
            Transfer.ComplianceStatus.ON_HOLD,
            Transfer.ComplianceStatus.REJECTED,
            Transfer.ComplianceStatus.UNDER_REVIEW,
        }:
            return None

        return PaymentFraudBreach(
            rule=rule,
            observed_value=instruction.transfer.compliance_status,
            details={
                "compliance_status": instruction.transfer.compliance_status,
                "payment_method": instruction.payment_method,
            },
        )

    return None


def create_payment_fraud_flag(
    instruction: TransferPaymentInstruction,
    breach: PaymentFraudBreach,
    *,
    changed_by=None,
) -> TransferComplianceFlag | None:
    rule = breach.rule
    metadata = {
        "rule_id": str(rule.id),
        "rule_type": rule.rule_type,
        "action": rule.action,
        "payment_instruction_id": str(instruction.id),
        "provider_name": instruction.provider_name,
        "provider_reference": instruction.provider_reference,
        "observed_value": breach.observed_value,
        **breach.details,
    }
    existing_flag = instruction.transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.PAYMENT,
        code=rule.code,
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    ).first()

    if existing_flag:
        existing_flag.severity = rule.severity
        existing_flag.title = f"Payment fraud rule triggered: {rule.name}"
        existing_flag.description = rule.description or (
            f"Configured {rule.get_rule_type_display()} payment fraud rule triggered."
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
        transfer=instruction.transfer,
        category=TransferComplianceFlag.Category.PAYMENT,
        severity=rule.severity,
        code=rule.code,
        title=f"Payment fraud rule triggered: {rule.name}",
        description=rule.description
        or f"Configured {rule.get_rule_type_display()} payment fraud rule triggered.",
        metadata=metadata,
        created_by=changed_by,
    )


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())
