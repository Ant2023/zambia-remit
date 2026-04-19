# Zambia Remit MVP Launch Checklist

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
```

## Frontend Environment

```env
DJANGO_API_BASE_URL=https://api.your-domain.com/api/v1
```

## Backend Pre-Deploy Commands

```powershell
cd "C:\Money Projects\zambia-remit\backend"
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_core_data
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
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
- Django admin works for staff at `/admin/`.
- `/api/v1/health/` returns `{"status":"ok"}`.
