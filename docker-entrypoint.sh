#!/bin/sh
set -e

echo "🚀 Starting..."

# Default to no migrations unless explicitly enabled per service.
RUN_MIGRATIONS=${RUN_MIGRATIONS:-false}

echo "Waiting for PostgreSQL..."
while ! python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('${DB_HOST}', int(${DB_PORT})))" 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is up!"

echo "Waiting for Redis..."
while ! python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('${REDIS_HOST}', int(${REDIS_PORT})))" 2>/dev/null; do
    sleep 1
done
echo "Redis is up!"

# Only migrate when explicitly enabled for this container.
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running migrations..."
    python manage.py migrate --noinput
fi

exec "$@"
