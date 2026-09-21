# ADR-004 — Ingestão controlada

Status: aceito.

Produtos entram somente por `manual`, `official_import` ou pela fronteira `approved_api`. Na Fase 2, `manual` é funcional, `official_import` significa exclusivamente CSV UTF-8 oficial fornecido pelo operador e `approved_api` não executa chamadas. Não existe integração direta com a Shopee e nenhum dado é obtido por scraping.

O arquivo tem limite de 5 MiB e 10.000 linhas, cabeçalho e colunas em allowlist. XLS/XLSX, macros e interpretação de fórmulas são proibidos. Uma linha inválida não invalida linhas válidas; erro estrutural reprova a requisição antes do batch. A idempotência combina chave, SHA-256 do payload e representação canônica.
