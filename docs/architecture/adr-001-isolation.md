# ADR-001 — Isolamento por redes e recursos próprios

Status: aceito.

O projeto usa PostgreSQL, Redis, volumes e redes próprios. `shopee_core` e `shopee_ops` são internas, não há `ports`, `network_mode: host`, privilégio, Docker socket ou conexão ao n8n. Isso reduz movimento lateral e elimina colisões com Traefik e serviços existentes. O custo é exigir `docker compose exec` para diagnóstico.
