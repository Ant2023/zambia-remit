import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create an encrypted PostgreSQL backup using pg_dump."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=str(settings.BACKUP_LOCAL_DIR),
            help="Directory for the encrypted backup artifact.",
        )

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if "postgresql" not in database["ENGINE"]:
            raise CommandError("backup_database only supports PostgreSQL databases.")

        backup_key = settings.BACKUP_ENCRYPTION_KEY
        if not backup_key:
            raise CommandError("BACKUP_ENCRYPTION_KEY is required for encrypted backups.")

        try:
            fernet = Fernet(backup_key.encode("ascii"))
        except (TypeError, ValueError) as exc:
            raise CommandError("BACKUP_ENCRYPTION_KEY must be a valid Fernet key.") from exc

        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
        plain_path = output_dir / f"mbongopay-{timestamp}.dump"
        encrypted_path = plain_path.with_suffix(".dump.fernet")

        env = os.environ.copy()
        env.update(
            {
                "PGHOST": str(database["HOST"]),
                "PGPORT": str(database["PORT"]),
                "PGUSER": str(database["USER"]),
                "PGPASSWORD": str(database["PASSWORD"]),
            },
        )

        try:
            subprocess.run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--file",
                    str(plain_path),
                    str(database["NAME"]),
                ],
                check=True,
                env=env,
                capture_output=True,
                text=True,
            )
            encrypted_path.write_bytes(fernet.encrypt(plain_path.read_bytes()))
        except FileNotFoundError as exc:
            raise CommandError("pg_dump was not found on PATH.") from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(exc.stderr or "pg_dump failed.") from exc
        finally:
            plain_path.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f"Encrypted backup created: {encrypted_path}"))
