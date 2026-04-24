# MbongoPay MVP Launch Checklist

## Deployment Order

1. Provision managed PostgreSQL.
2. Deploy Django backend with production environment variables.
3. Run backend migrations, seed core data, and create a staff superuser.
4. Run `collectstatic`.
5. Confirm `/api/v1/health/` returns `{"status":"ok"}`.
6. Deploy the Next.js frontend with `DJANGO_API_BASE_URL` pointing to the backend.
7. Run the end-to-end customer flow in production.

## Backend Environment

```env
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.your-domain.com,your-backend-host.amazonaws.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-frontend-domain.com,https://api.your-domain.com

POSTGRES_DB=zambia_remit
POSTGRES_USER=zambia_remit_user
POSTGRES_PASSWORD=replace-with-a-strong-password
POSTGRES_HOST=your-rds-hostname.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=60

DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True
AUTH_TOKEN_TTL_HOURS=168
FIELD_ENCRYPTION_KEY=replace-with-fernet-key-generated-by-python

SECURE_DOCUMENT_MAX_UPLOAD_SIZE=10485760
SECURE_DOCUMENT_ALLOWED_CONTENT_TYPES=application/pdf,image/jpeg,image/png
SECURE_DOCUMENT_STORAGE_ROOT=/var/lib/mbongopay/private_documents

CARD_PAYMENT_PROCESSOR=hosted_card_provider
BANK_TRANSFER_PAYMENT_PROCESSOR=manual_bank_transfer
PAYMENT_PROVIDER_CONFIGS={"hosted_card_provider":{"display_name":"Hosted card provider","base_url":"https://api.payment-provider.example","api_key":"replace-with-payment-api-key","create_session_path":"/checkout/sessions","checkout_url":"https://checkout.payment-provider.example"}}
PAYMENT_WEBHOOK_SECRETS=hosted_card_provider:replace-with-payment-webhook-secret
PAYOUT_WEBHOOK_SECRETS=provider-code:replace-with-payout-webhook-secret

BACKUP_REQUIRED=True
BACKUP_STORAGE_URL=s3://your-private-backup-bucket/postgres
BACKUP_ENCRYPTION_KEY=replace-with-fernet-backup-key
BACKUP_RETENTION_DAYS=30
BACKUP_LOCAL_DIR=/var/backups/mbongopay
```

## Frontend Environment

```env
DJANGO_API_BASE_URL=https://api.your-domain.com/api/v1
```

## Backend Pre-Deploy Commands

```powershell
cd "C:\Money Projects\zambia-remit\backend"
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check --deploy
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_core_data
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Generate Fernet keys for `FIELD_ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY` with:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Run encrypted database backups from a host with `pg_dump` available:

```powershell
.\.venv\Scripts\python.exe manage.py backup_database
```

## Frontend Pre-Deploy Commands

```powershell
cd "C:\Money Projects\zambia-remit\frontend"
npm run build
```

## Final Smoke Test

- Customer can create an account at `/login`.
- Staff account cannot log in through the customer login form.
- Customer can choose sender country, Zambia destination, and send amount.
- Rate and receive amount appear before recipient entry.
- Customer can create a recipient.
- Customer can prepare and review transaction details.
- Customer can create a transaction.
- Customer lands on funding.
- Customer can mark funding received.
- Success page shows funding received.
- History shows one aligned row per transfer.
- Transfer detail shows status history.
- A second customer cannot view the first customer's transfer detail URL.
- Sender document uploads accept only PDF/JPEG/PNG files and do not expose media URLs.
- Staff document review/download requires the sender document role permissions.
- `manage.py check --deploy` passes with explicit encryption, webhook, and backup settings.
- Django admin works for staff at `/admin/`.
- `/api/v1/health/` returns `{"status":"ok"}`.
- `/api/v1/health/ready/` returns `{"status":"ready"}` when the database is reachable.
