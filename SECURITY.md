# Política de segurança

Relate vulnerabilidades de forma privada aos mantenedores do repositório. Não abra issues públicas com tokens, credenciais, dumps ou detalhes exploráveis.

Nunca inclua segredos em commits ou logs. Em caso de exposição, revogue e rotacione primeiro, preserve evidências sem copiar o segredo e registre o incidente em canal privado. Dependências são verificadas com `pip-audit`; o CI também executa detecção de segredos.

Consulte `docs/security/secrets-policy.md` e `docs/security/threat-model.md`.
