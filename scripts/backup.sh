#!/bin/sh
set -eu

backup_dir=${1:-./backups}
mkdir -p "$backup_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="$backup_dir/shopee_affiliate_$timestamp.dump"

docker compose exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "$output"
chmod 600 "$output"
printf '%s\n' "$output"
