# Modelo de dados da Fase 2

- `ImportBatch` controla origem, hash, chave idempotente, contagens e ciclo da importação.
- `ImportRow` preserva entrada autorizada, normalização, erro sanitizado e vínculos resultantes.
- `Product` permanece único por `source + external_id`; `ProductSnapshot` preserva fatos comerciais históricos.
- `ProductAssessment` registra sete dimensões decimais e evidências para um snapshot do mesmo produto.
- `ProductScore` guarda pesos, componentes e total imutável calculado pela regra versionada.
- `ProductOpportunity` preserva recomendação, validade e decisão humana com versionamento otimista.
- `OperationalAlert` representa condição interna reconhecível e resolvível.
- `AuditEvent` registra eventos append-only de todas as decisões e mudanças relevantes.

Constraints e triggers PostgreSQL validam ranges, relações entre produto/snapshot/assessment/score/oportunidade, contagens finais, timestamps, imutabilidade e transições. UUIDs e timestamps UTC são usados em todo o domínio; valores comerciais usam `Numeric`/`Decimal`.
