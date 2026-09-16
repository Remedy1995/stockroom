# Stockroom

Stockroom is a production-minded REST API and small demonstration client for a workspace inventory product. A reviewer can create a workspace, sign in, manage products, and inspect the live OpenAPI contract.

## What it demonstrates

- Argon2 password hashing, opaque bearer tokens, HttpOnly cookie sessions, logout, session revocation, password rotation, and expiring verification/reset links.
- Workspace-scoped inventory CRUD with SKU uniqueness, validation, pagination, filtering, search, low-stock status, audit history, and CSV export.
- Owner, editor, and viewer roles. Every record query includes the caller's workspace, so records from another workspace return `404`.
- Optimistic locking: updates and deletes require the current `version`, preventing silent overwrite when two users edit a product.
- Request IDs, structured errors, restrictive CORS and hosts, CSRF origin checks for cookie sessions, body-size limits, persisted rate limits, security headers, health probes, migrations, CI, and Docker configuration.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) for the demo client and [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the API reference.

## API guide

Create an account:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Jordan Doe","workspace":"North Star","email":"jordan@example.com","password":"a-secure-password-123"}'
```

The response includes an opaque `access_token`. Supply it to non-browser clients:

```bash
curl http://127.0.0.1:8000/api/v1/products \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Amounts are integer cents (`price_cents`) and timestamps are Unix seconds. A product `PUT` body must include the current `version`; a stale version receives `409`.

## Verify

```bash
.venv/bin/ruff check app tests
.venv/bin/pytest -q
.venv/bin/pip-audit -r requirements.txt
```

## Production deployment

Set `ENVIRONMENT=production`, an explicit PostgreSQL `DATABASE_URL`, HTTPS `ALLOWED_ORIGINS`, explicit `ALLOWED_HOSTS`, and `SECURE_COOKIES=true`. Unsafe production values are rejected at startup. `compose.yaml` is a template: replace its placeholder hostname and database password before deployment.

```bash
docker compose up --build
```

## Competition submission

Use [docs/submission.md](docs/submission.md) for the form description. The transcribed requirements are in [docs/challenge.md](docs/challenge.md), and the recording walkthrough is in [docs/demo-script.md](docs/demo-script.md). Add the public repository and uploaded-video URLs after publishing.
