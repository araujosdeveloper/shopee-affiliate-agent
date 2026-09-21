# Modelo de ameaças

Ativos: credenciais, links afiliados, conteúdo, decisões, métricas e dados de operadores. Fronteiras: cliente–API, aplicação–PostgreSQL, aplicação–Redis e operador–Docker.

Principais ameaças e controles:

- acesso indevido à API: Bearer token, comparação constante, rede interna e respostas sem detalhes;
- vazamento de segredo: `.env` ignorado e `0600`, redaction por desenho, secret scanning e credenciais separadas;
- adulteração de auditoria: revogação de UPDATE/DELETE/TRUNCATE e trigger append-only;
- publicação indevida: aprovação humana, snapshot recente, disponibilidade e automação bloqueada em várias camadas;
- movimento lateral: redes internas, capacidades removidas, non-root na aplicação, no-new-privileges e ausência do Docker socket;
- cadeia de suprimentos: versões fixadas, imagem base fixa por tag e `pip-audit` no CI;
- exaustão: limites de CPU/memória, concorrência 1, prefetch 1 e Redis sem eviction.

Risco residual: Bearer token único não oferece identidade individual; tags de imagem não são imutáveis como digest; logs ainda dependem do acesso ao daemon Docker. Esses pontos devem ser tratados antes de exposição externa.
