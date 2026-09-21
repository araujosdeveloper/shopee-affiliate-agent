# Visão geral da arquitetura

A Fase 2 permanece deliberadamente fechada. API, worker e Celery Beat compartilham apenas a rede interna `shopee_core` com PostgreSQL e Redis. O serviço efêmero de migração também usa `shopee_ops`. Nenhuma porta é publicada no host.

O FastAPI expõe liveness, readiness e a API autenticada. O worker Celery tem concorrência 1, ack após persistência, retry limitado e processa somente dados recebidos. O Beat executa rotinas internas a cada 15 minutos. PostgreSQL mantém estado, snapshots históricos, scores imutáveis e auditoria append-only; Redis atende broker, backend e readiness.

O fluxo é `fonte autorizada → ImportBatch/ImportRow → Product/ProductSnapshot → ProductAssessment → ProductScore → ProductOpportunity`. Ranking usa allowlist e desempate determinístico. Shortlist e descarte são exclusivamente humanos e oportunidade alguma produz publicação.

Snapshots preservam a origem autorizada do dado e as aprovações registram a versão exata do conteúdo analisado. A autorização de publicação verifica essas relações no domínio e no banco; alterar o conteúdo depois da aprovação invalida a decisão anterior.

As fronteiras de domínio impedem scraping, fontes desconhecidas, preços sem instante de coleta, alegações inventadas, publicação sem aprovação humana e snapshot recente, disparo em massa, redirecionamento automático e compra pelo próprio link. O banco repete invariantes críticos para defesa em profundidade.
