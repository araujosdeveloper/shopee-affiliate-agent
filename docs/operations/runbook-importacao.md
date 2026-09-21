# Runbook de importação

1. Valide o CSV pelo contrato em `docs/contracts/official-import-csv.md`.
2. Envie para `POST /api/v1/imports/official` com Bearer token, `Idempotency-Key` e `X-Operator-ID`.
3. Consulte batch e linhas; a listagem omite `raw_data`.
4. Mesma chave retorna o batch original; mesmo payload com nova chave não cria snapshots duplicados.
5. Corrija rejeições na origem. Nunca inclua segredos, cookies ou dados de compradores.

Cadastro manual usa `/api/v1/imports/manual` e nunca infere `official_import`.
