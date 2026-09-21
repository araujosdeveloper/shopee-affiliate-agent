# Instruções para agentes

- Trabalhar somente em `/opt/shopee-affiliate-agent` e na branch `feat/foundation` durante a Fase 1.
- Não publicar portas, conectar redes externas, acessar `docker.sock` ou modificar serviços alheios.
- Não implementar scraping, integrações Shopee, mensageria externa ou publicação automática.
- Código e mensagens técnicas devem ser em inglês; documentação operacional, em português.
- Segredos pertencem somente ao `.env` ignorado. Nunca registrar valores secretos.
- Toda mudança de schema exige migração Alembic e testes.
- Aprovação humana e auditoria append-only são invariantes do domínio.
