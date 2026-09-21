# Limitação de proteção da `main`

Verificação em 2026-09-21 via GitHub CLI no repositório privado `araujosdeveloper/shopee-affiliate-agent`:

- proteção clássica de branch: HTTP 403;
- rulesets do repositório: HTTP 403;
- resposta da API: é necessário GitHub Pro ou tornar o repositório público.

Por determinação operacional, a limitação não foi contornada. Quando o recurso estiver disponível, configurar `main` para bloquear desenvolvimento direto e exigir os checks `quality-and-unit-tests` e `containers-and-integration`, sem aprovação obrigatória de terceiro para este repositório de operador único.
