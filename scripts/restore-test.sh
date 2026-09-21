#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: scripts/restore-test.sh BACKUP_FILE" >&2
  exit 2
fi

backup_file=$1
test_db="restore_test_$(date -u +%s)"
cleanup() {
  docker compose exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$test_db" >/dev/null
}
trap cleanup EXIT INT TERM

docker compose exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" createdb -U "$POSTGRES_USER" "$1"' sh "$test_db"
docker compose exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl' sh "$test_db" \
  < "$backup_file"
docker compose exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM alembic_version"' sh "$test_db" \
  | grep -qx '1'
echo "Isolated restore test passed"
