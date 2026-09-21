# Instruções para agentes

- Trabalhar somente em `/opt/shopee-affiliate-agent` e na branch `feat/controlled-ingestion` durante a Fase 2.
- Não publicar portas, conectar redes externas, acessar `docker.sock` ou modificar serviços alheios.
- Não implementar scraping, integrações Shopee, mensageria externa ou publicação automática.
- Código e mensagens técnicas devem ser em inglês; documentação operacional, em português.
- Segredos pertencem somente ao `.env` ignorado. Nunca registrar valores secretos.
- Toda mudança de schema exige migração Alembic e testes.
- Aprovação humana e auditoria append-only são invariantes do domínio.
- A ingestão aceita somente `manual`, arquivo `official_import` fornecido pelo operador e o contrato inativo `approved_api`.
- Não habilitar egress, scraping, publicação, mensageria, IA generativa ou integrações externas na Fase 2.
