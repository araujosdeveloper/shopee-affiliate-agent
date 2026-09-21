# Política de segredos

Segredos locais vivem somente em `.env`, com modo `0600`, gerados por `scripts/generate-env.sh`. `.env.example` contém apenas nomes e valores não secretos. Produção deverá usar um gerenciador de segredos, nunca o repositório ou variáveis em documentação.

Não imprimir, copiar para issues, incluir em comandos versionados ou salvar em backups os valores. Rotacionar imediatamente após suspeita de exposição. As credenciais administrativas, de migração e da aplicação são distintas; a aplicação não pode alterar nem apagar auditoria. O Redis exige senha.
