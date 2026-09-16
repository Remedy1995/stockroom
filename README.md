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

### Render public deployment

The repository includes `render.yaml` for a Docker web service and managed PostgreSQL database. The public deployment is available at [stockroom-api-remedy1995.onrender.com](https://stockroom-api-remedy1995.onrender.com). Its interactive Swagger documentation is at [/docs](https://stockroom-api-remedy1995.onrender.com/docs).

```text
ALLOWED_ORIGINS=["https://stockroom-api-remedy1995.onrender.com"]
ALLOWED_HOSTS=["stockroom-api-remedy1995.onrender.com"]
```

Render supplies the PostgreSQL connection string and assigned `PORT`; the image runs migrations before starting the API. Use `/health/ready` as the health check. The free service is suitable for a judge-accessible demo, though it can spin down when idle and free PostgreSQL is time-limited.

The repository's `keep-render-awake` GitHub Actions workflow requests `/health/ready` every five minutes to keep the free demo service active. GitHub schedules are best effort and public-repository schedules are disabled after 60 days without repository activity, so upgrade the service for a production availability guarantee.

## Competition submission

Use [docs/submission.md](docs/submission.md) for the form description. The transcribed requirements are in [docs/challenge.md](docs/challenge.md), and the recording walkthrough is in [docs/demo-script.md](docs/demo-script.md). Add the public repository and uploaded-video URLs after publishing.

Public repository: [github.com/Remedy1995/stockroom](https://github.com/Remedy1995/stockroom). Live API: [stockroom-api-remedy1995.onrender.com](https://stockroom-api-remedy1995.onrender.com). Swagger: [/docs](https://stockroom-api-remedy1995.onrender.com/docs). The demo video is included at [submission/stockroom-api-demo.mp4](submission/stockroom-api-demo.mp4).
