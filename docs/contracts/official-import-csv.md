# Contrato do CSV de importação oficial

Codificação UTF-8, conteúdo `text/csv`, máximo 5 MiB e 10.000 registros. Cabeçalho obrigatório.

Obrigatórias: `external_id,title,price,currency,available,collected_at`.

Opcionais: `canonical_url,category,source_payload_hash`.

Colunas desconhecidas são rejeitadas. `currency` aceita apenas `BRL`; preço tem duas casas; `available` é `true` ou `false`; coleta usa ISO 8601 com timezone e não pode ser futura. URL deve ser HTTPS sem credenciais e nunca é seguida. Fórmulas permanecem texto. XLS/XLSX e macros não são aceitos.

`official_import` significa arquivo oficial entregue pelo operador, nunca download automatizado.
