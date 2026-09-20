# Visão geral da arquitetura

A Fase 1 é deliberadamente fechada. API e worker compartilham apenas a rede interna `shopee_core` com PostgreSQL e Redis. O serviço efêmero de migração também usa `shopee_ops`. Nenhuma rede tem saída externa e nenhuma porta é publicada no host.

O FastAPI expõe liveness, readiness e status interno. O worker Celery tem concorrência 1, serialização JSON e nenhuma tarefa de integração. O PostgreSQL mantém o estado transacional e a trilha append-only; o Redis atende broker, backend e readiness. A migração executa com credencial separada da aplicação.

As fronteiras de domínio impedem scraping, fontes desconhecidas, preços sem instante de coleta, alegações inventadas, publicação sem aprovação humana e snapshot recente, disparo em massa, redirecionamento automático e compra pelo próprio link. O banco repete invariantes críticos para defesa em profundidade.
