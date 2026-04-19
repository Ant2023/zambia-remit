# Zambia Remit MVP Deployment and E2E Checklist

## Local PostgreSQL Setup

1. Create a local PostgreSQL database named `zambia_remit`.
2. Confirm `backend/.env` contains:

```env
DJANGO_SETTINGS_MODULE=config.settings.dev
POSTGRES_DB=zambia_remit
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=0
```

3. Run migrations and seed data:

```powershell
cd "C:\Money Projects\zambia-remit\backend"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_core_data
```

4. Create a staff admin account for Django admin:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

## Backend Deployment Readiness

- Use `config.settings.prod`.
- Set a strong `DJANGO_SECRET_KEY`.
- Set `DJANGO_ALLOWED_HOSTS` to the backend host names.
- Set `DJANGO_CSRF_TRUSTED_ORIGINS` to the frontend and backend HTTPS origins.
- Use managed PostgreSQL in production.
- Run `manage.py migrate` during deployment.
- Run `manage.py collectstatic` during deployment.
- Serve `STATIC_ROOT` through the platform, CDN, or reverse proxy.
- Keep uploaded media on external storage before adding user-uploaded files.
- Keep Django admin limited to staff accounts.

## Frontend Deployment Readiness

- Set `DJANGO_API_BASE_URL` to the deployed Django API base URL.
- Keep browser calls pointed at the Next.js proxy route: `/api/django/...`.
- Do not expose Django admin credentials in the frontend.
- Confirm the frontend deployment can reach the backend from the server runtime.

## E2E Checklist

1. Customer auth:
   - Open `/login`.
   - Create a customer account.
   - Log out from the main page.
   - Log back in with the same customer account.
   - Confirm staff/admin accounts cannot log in through the customer form.

2. Recipient:
   - Select sender country and Zambia as destination.
   - Enter send amount.
   - Confirm exchange rate and receive estimate appear.
   - Create a mobile money recipient with MTN or Airtel.
   - Repeat once with bank deposit if needed.

3. Quote:
   - Prepare transaction details.
   - Confirm send amount, rate, receive amount, total amount, provider, reason, and recipient details.

4. Transfer:
   - Click `Create transaction`.
   - Confirm the app routes to `/funding?transferId=...`.
   - Confirm transfer status is `Awaiting funding`.

5. Funding:
   - Choose `Debit card` or `Bank transfer`.
   - Click `Mark as funded`.
   - Confirm status changes to `Funding received`.
   - Confirm a status event is added.

6. Success:
   - Confirm the success page shows the transfer reference.
   - Confirm funding status is `Received`.

7. History:
   - Open `/history`.
   - Confirm the transfer appears once.
   - Confirm columns align: Reference, Status, Funding, Send amount, Receive amount, Created, Action.

8. Transfer detail:
   - Open a transfer from history.
   - Confirm reference, status, funding, amounts, created date, and status history display.

9. Ownership/security:
   - Log in as a second customer.
   - Confirm the second customer cannot see the first customer's recipients, quotes, transfers, or transfer detail URLs.
