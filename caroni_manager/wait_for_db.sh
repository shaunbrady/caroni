#!/bin/sh
set -e

RETRIES=20
DELAY=2

echo "Waiting for database at $DB_HOST:$DB_PORT..."

for i in $(seq 1 $RETRIES); do
    if python - <<EOF
import psycopg, os
from urllib.parse import urlparse
url = urlparse(os.environ["DATABASE_URL"])
try:
    conn = psycopg.connect(
        host=url.hostname,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=url.path[1:],
        connect_timeout=1
    )
    conn.close()
except Exception:
    raise
EOF
    then
        echo "Database is ready!"
        exec "$@"
        exit 0
    fi

    echo "Database not ready, retrying ($i/$RETRIES)..."
    sleep $DELAY
done

echo "Database never became ready!"
exit 1