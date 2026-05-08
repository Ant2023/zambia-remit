import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationalAuditLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action_name", models.CharField(max_length=120)),
                ("target_type", models.CharField(max_length=120)),
                ("target_id", models.CharField(blank=True, max_length=80)),
                ("target_reference", models.CharField(blank=True, max_length=120)),
                ("previous_status", models.CharField(blank=True, max_length=80)),
                ("new_status", models.CharField(blank=True, max_length=80)),
                ("note", models.TextField(blank=True)),
                ("request_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=512)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="operational_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(
                        fields=["action_name", "created_at"],
                        name="common_oper_action__52bd8c_idx",
                    ),
                    models.Index(
                        fields=["target_type", "target_id"],
                        name="common_oper_target__7e737c_idx",
                    ),
                    models.Index(
                        fields=["actor", "created_at"],
                        name="common_oper_actor_i_37a562_idx",
                    ),
                    models.Index(
                        fields=["target_reference"],
                        name="common_oper_target__15d11d_idx",
                    ),
                ],
            },
        ),
    ]
