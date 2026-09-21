# Shopee Affiliate Agent

Plataforma determinística para ingestão controlada e inteligência comercial, com compliance por padrão. Na Fase 2, produtos entram apenas por cadastro `manual` ou CSV `official_import` fornecido pelo operador. `approved_api` é somente uma fronteira futura e não realiza chamadas. Não há integração direta com a Shopee, scraping, publicação, mensageria, IA generativa ou egress externo.

## Componentes

- API FastAPI interna, protegida por Bearer token em `/api/v1/*`.
- Worker Celery com concorrência 1 e Beat separado a cada 15 minutos, sem tarefas externas.
- PostgreSQL 16 exclusivo, com migrações Alembic e usuário de aplicação limitado.
- Redis 7.4.2 exclusivo e autenticado.
- Redes Docker internas, sem nenhuma porta publicada.

## Início rápido

```bash
./scripts/generate-env.sh
docker compose config --quiet
docker compose build
docker compose up -d --wait
docker compose --profile test run --rm test
```

O arquivo `.env` local é ignorado pelo Git e deve permanecer com modo `0600`. Consulte os runbooks em `docs/operations/` antes de operar o ambiente.

## API

- `GET /health/live`: verifica somente o processo.
- `GET /health/ready`: verifica PostgreSQL e Redis.
- `GET /api/v1/system/status`: requer `Authorization: Bearer <token>`.
- OpenAPI: `/docs` e `/openapi.json`, acessíveis apenas pela rede interna do container.

Todos os endpoints `/api/v1` exigem Bearer token. Mutações exigem `Idempotency-Key` quando aplicável e ações humanas usam `X-Operator-ID`. Oportunidades são recomendações internas; shortlist exige ação humana e nunca produz publicação.

## Validação

```bash
make validate
docker compose --profile test run --rm test
./scripts/check-readiness-failure.sh
backup=$(./scripts/backup.sh /tmp/shopee-backups)
./scripts/restore-test.sh "$backup"
```
