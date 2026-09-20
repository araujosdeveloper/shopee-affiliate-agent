#!/bin/sh
set -eu

cleanup() { docker compose start redis >/dev/null; }
trap cleanup EXIT INT TERM

docker compose stop redis >/dev/null
docker compose exec -T api python -c "
import json
import urllib.error
import urllib.request
try:
    urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)
except urllib.error.HTTPError as exc:
    assert exc.code == 503
    body = json.loads(exc.read())
    assert body['status'] == 'not_ready'
    assert body['dependencies']['redis'] == 'unavailable'
else:
    raise SystemExit('readiness unexpectedly succeeded')
"
echo "Readiness failure behavior passed"
