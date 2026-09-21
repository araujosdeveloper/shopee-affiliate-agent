# Contrato OpenAPI

O contrato canônico gerado pelo FastAPI está em `/openapi.json` na rede interna. A API usa `/api/v1`, paginação padrão 50 e máxima 200.

Todos os endpoints v1 exigem autenticação. Mutações idempotentes exigem `Idempotency-Key`; ações humanas também usam `X-Operator-ID`. Erros usam `{ "error": { "code", "message" }, "request_id" }` e nunca incluem traceback, conexão, segredo ou payload bruto.

`POST /api/v1/products` é exclusivamente manual e não aceita `source` no payload.
`POST /api/v1/products/{id}/snapshots` aceita apenas produtos manuais. Tentativas de
forjar procedência retornam `validation_error` ou `unsupported_source`; conflitos de
replay retornam `idempotency_conflict` (HTTP 409). `source_payload_hash`, quando
presente, deve ser SHA-256 hexadecimal de 64 caracteres e é normalizado para
minúsculas.

Replays com a mesma chave, operação, ator, entidade e payload retornam o recurso já
produzido sem nova alteração, incremento de versão ou auditoria. Reuso da chave em
outro contexto retorna `idempotency_conflict`.

Identificadores presentes na URL integram o contexto idempotente. Assim, a mesma
chave e corpo usados com outro `product_id`, `batch_id`, `assessment_id`, `score_id`,
`opportunity_id` ou `alert_id` retornam `idempotency_conflict`.

`source_payload_hash` preserva exclusivamente o hash declarado pela fonte. A
identidade interna de snapshots usa `ProductSnapshot.idempotency_key` no formato
`canonical:{digest}`. Reutilizar o hash declarado com conteúdo comercial diferente
retorna `source_payload_hash_conflict`.
