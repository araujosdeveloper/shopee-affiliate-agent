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
