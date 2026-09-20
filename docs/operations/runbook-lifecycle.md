# Runbook de subida e desligamento

## Subida

1. Confirme a branch e que nenhuma porta está configurada: `git branch --show-current` e `docker compose config`.
2. Se necessário, execute `./scripts/generate-env.sh` uma única vez.
3. Execute `docker compose build`.
4. Execute `docker compose up -d --wait`. A migração termina antes da API e worker.
5. Verifique `docker compose ps`, logs e `docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').status)"`.

## Desligamento

Use `docker compose down`. Isso preserva os volumes. Nunca use `-v` sem procedimento formal de descarte. Não execute comandos globais de prune e não pare containers fora deste projeto.
