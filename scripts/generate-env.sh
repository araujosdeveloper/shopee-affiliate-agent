#!/bin/sh
set -eu

if [ -e .env ]; then
  echo ".env already exists; refusing to overwrite" >&2
  exit 1
fi

umask 077
random_secret() { openssl rand -base64 48 | tr -d '\n'; }

{
  printf '%s\n' 'APP_ENV=development' 'LOG_LEVEL=INFO'
  printf 'INTERNAL_API_TOKEN=%s\n' "$(random_secret)"
  printf '%s\n' 'POSTGRES_DB=shopee_affiliate' 'POSTGRES_ADMIN_USER=postgres_admin'
  printf 'POSTGRES_ADMIN_PASSWORD=%s\n' "$(random_secret)"
  printf '%s\n' 'POSTGRES_MIGRATION_USER=shopee_migrator'
  printf 'POSTGRES_MIGRATION_PASSWORD=%s\n' "$(random_secret)"
  printf '%s\n' 'POSTGRES_APP_USER=shopee_app'
  printf 'POSTGRES_APP_PASSWORD=%s\n' "$(random_secret)"
  printf 'REDIS_PASSWORD=%s\n' "$(random_secret)"
  printf '%s\n' \
    'BUSINESS_TIMEZONE=America/Sao_Paulo' \
    'AUTO_PUBLICATION_ENABLED=false' \
    'HUMAN_APPROVAL_REQUIRED=true' \
    'PRICE_VALIDATION_MAX_AGE_MINUTES=60' \
    'SCORE_WEIGHT_CONVERSION_POTENTIAL=30' \
    'SCORE_WEIGHT_NET_COMMISSION=20' \
    'SCORE_WEIGHT_PRODUCT_QUALITY=15' \
    'SCORE_WEIGHT_PRICE_STOCK_STABILITY=10' \
    'SCORE_WEIGHT_NICHE_FIT=10' \
    'SCORE_WEIGHT_VIDEO_DEMONSTRATION_POTENTIAL=10' \
    'SCORE_WEIGHT_CANCELLATION_QUALITY=5'
} > .env

echo "Created .env with mode 0600"
