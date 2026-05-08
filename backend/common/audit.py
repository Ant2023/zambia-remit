import logging
from typing import Any

from django.contrib.auth.models import AnonymousUser

from .models import OperationalAuditLog


logger = logging.getLogger("mbongopay.security")
MAX_AUDIT_NOTE_LENGTH = 1000


def record_operational_audit(
    *,
    action_name: str,
    target_type: str,
    request=None,
    actor=None,
    target_id: str = "",
    target_reference: str = "",
    previous_status: str = "",
    new_status: str = "",
    note: str = "",
    metadata: dict[str, Any] | None = None,
) -> OperationalAuditLog | None:
    """Record a safe internal trace of staff operations without storing raw provider payloads."""
    try:
        audit_actor = actor or _get_request_actor(request)
        return OperationalAuditLog.objects.create(
            actor=audit_actor,
            action_name=action_name,
            target_type=target_type,
            target_id=str(target_id) if target_id else "",
            target_reference=str(target_reference) if target_reference else "",
            previous_status=str(previous_status) if previous_status else "",
            new_status=str(new_status) if new_status else "",
            note=(note or "")[:MAX_AUDIT_NOTE_LENGTH],
            request_ip=_get_request_ip(request),
            user_agent=_get_user_agent(request),
            metadata=metadata or {},
        )
    except Exception:
        logger.exception("Operational audit log write failed for %s", action_name)
        return None


def _get_request_actor(request):
    user = getattr(request, "user", None)

    if not user or isinstance(user, AnonymousUser):
        return None

    if getattr(user, "is_authenticated", False):
        return user

    return None


def _get_request_ip(request):
    meta = getattr(request, "META", {}) if request else {}
    forwarded_for = meta.get("HTTP_X_FORWARDED_FOR", "")
    value = forwarded_for.split(",")[0].strip() if forwarded_for else ""

    return value or meta.get("REMOTE_ADDR") or None


def _get_user_agent(request):
    meta = getattr(request, "META", {}) if request else {}
    return (meta.get("HTTP_USER_AGENT") or "")[:512]
