import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class OperationalAuditLog(BaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="operational_audit_logs",
        null=True,
        blank=True,
    )
    action_name = models.CharField(max_length=120)
    target_type = models.CharField(max_length=120)
    target_id = models.CharField(max_length=80, blank=True)
    target_reference = models.CharField(max_length=120, blank=True)
    previous_status = models.CharField(max_length=80, blank=True)
    new_status = models.CharField(max_length=80, blank=True)
    note = models.TextField(blank=True)
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("action_name", "created_at")),
            models.Index(fields=("target_type", "target_id")),
            models.Index(fields=("actor", "created_at")),
            models.Index(fields=("target_reference",)),
        ]

    def __str__(self) -> str:
        target = self.target_reference or self.target_id
        return f"{self.action_name}: {target}"
