# Shopee Affiliate Agent

Fundação determinística para operações internas de conteúdo afiliado, com compliance por padrão. A Fase 1 não integra com a Shopee, não faz scraping e não publica conteúdo.

## Componentes

- API FastAPI interna, protegida por Bearer token em `/api/v1/*`.
- Worker Celery com concorrência 1 e sem tarefas externas nesta fase.
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

## Validação

```bash
make validate
docker compose --profile test run --rm test
./scripts/check-readiness-failure.sh
backup=$(./scripts/backup.sh /tmp/shopee-backups)
./scripts/restore-test.sh "$backup"
```
