# Auth Service OTP

Email-based OTP authentication service built with Django, DRF, Redis, Celery, PostgreSQL, JWT, and drf-spectacular.

## Prerequisites

- Docker
- Docker Compose (plugin or standalone)

Optional for bare-metal development:

- Python 3.12+
- PostgreSQL
- Redis

## Quick Start (Docker)

1. Clone the project and enter the directory.

```bash
git clone https://github.com/LexxLuey/auth-service-otp.git
cd auth_service_otp
```

1. Create Docker env file from template.

```bash
cp .env.example .env
```

1. Start all services.

```bash
docker compose up --build
```

OR if using another .env file

```bash
docker compose --env-file .env.docker up --build
```

1. Open:

- API root: <http://localhost:8000/api/v1/>
- Swagger UI: <http://localhost:8000/api/docs/>
- Admin: <http://localhost:8000/admin>

## Bare Metal Quick Start

1. Clone and enter the project.

```bash
git clone https://github.com/LexxLuey/auth-service-otp.git
cd auth_service_otp
```

1. Create and activate a virtual environment.

```bash
python -m venv venv
source venv/bin/activate
```

1. Install requirements.

```bash
pip install -r requirements.dev.txt
```

1. Create local environment file.

```bash
cp .env.example .env
```

1. Run migrations.

```bash
python manage.py migrate
```

1. Start Redis (separate terminal), Celery worker, and Django app.

```bash
redis-server
celery -A config worker --loglevel=info
python manage.py runserver
```

## Environment Variables

Use `.env.example` as the source of truth for required variables.

Core variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `JWT_ACCESS_TOKEN_LIFETIME`, `JWT_REFRESH_TOKEN_LIFETIME`, `JWT_ALGORITHM`

## API Documentation

Swagger UI is available at:

- <http://localhost:8000/api/docs/>

OpenAPI schema endpoint:

- <http://localhost:8000/api/schema/>

## API Endpoints

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/api/v1/` | GET | API information | None |
| `/api/v1/health` | GET | Health check | None |
| `/api/v1/auth/otp/request` | POST | Request OTP | None |
| `/api/v1/auth/otp/verify` | POST | Verify OTP and issue JWT | None |
| `/api/v1/audit/logs` | GET | List audit logs | JWT |

Status summary:

- `POST /api/v1/auth/otp/request`: `202`, `429`, `503`
- `POST /api/v1/auth/otp/verify`: `200`, `400`, `423`, `503`
- `GET /api/v1/audit/logs`: `200`, `400`, `401`

## Project Structure

```text
.
├── apps/
│   ├── accounts/      # OTP request/verify, user and token services
│   └── audit/         # Audit model, filters, read-only logs endpoint
├── config/            # Django settings, URLs, Celery app
├── templates/
├── docker-compose.yml
├── Dockerfile
├── docker-entrypoint.sh
├── requirements.txt
├── requirements.dev.txt
└── .env.example
```

## Testing

Run tests in Docker:

```bash
docker compose exec web python manage.py test
```

OR if using another .env file

```bash
docker compose --env-file .env.docker exec web python manage.py test
```

Run tests on bare metal:

```bash
python manage.py test
```

Requirements files:

- `requirements.txt`: runtime dependencies
- `requirements.dev.txt`: development and testing dependencies

## Troubleshooting

1. Celery container runs migrations unexpectedly

- Cause: stale Docker image with old `docker-entrypoint.sh`.
- Fix: rebuild images when `Dockerfile` or `docker-entrypoint.sh` changes.

1. Tests fail with PostgreSQL connection errors on bare metal

- Cause: local DB is not running or env points to wrong host.
- Fix: start PostgreSQL and ensure `DB_*` values match local setup, or run tests inside Docker.

1. `from_date` / `to_date` filter returns `400`

- Cause: invalid datetime format in query string.
- Fix: use ISO datetime values, e.g. `2026-03-02T12:00:00Z`.

1. Redis warning about memory overcommit

- Message appears in Redis logs: `vm.overcommit_memory`.
- Fix (host-level): set `vm.overcommit_memory=1` as recommended by Redis docs.

1. Celery warning about running as root

- This appears in container logs for local dev.
- For production, run worker with a non-root user.

## Notes

- All major API paths include drf-spectacular docs with request/response examples.
- Architecture follows modular Django app boundaries (`accounts`, `audit`) and 12-factor style env-based config.
