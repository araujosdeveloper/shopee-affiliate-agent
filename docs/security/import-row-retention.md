# Retenção de `ImportRow.raw_data`

`raw_data` conserva somente colunas permitidas para investigação. Credenciais, cookies e dados pessoais de compradores são proibidos. A API de listagem nunca retorna esse campo.

Retenção inicial: 30 dias após conclusão. A rotina futura de descarte deverá substituir o conteúdo por marcador sem apagar linha, hash, status ou vínculos, e registrar auditoria. Até existir, importar somente o mínimo necessário.
