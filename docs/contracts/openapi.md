# Contrato OpenAPI

O contrato canônico gerado pelo FastAPI está em `/openapi.json` na rede interna. A API usa `/api/v1`, paginação padrão 50 e máxima 200.

Todos os endpoints v1 exigem autenticação. Mutações idempotentes exigem `Idempotency-Key`; ações humanas também usam `X-Operator-ID`. Erros usam `{ "error": { "code", "message" }, "request_id" }` e nunca incluem traceback, conexão, segredo ou payload bruto.
