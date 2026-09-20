# Runbook de backup e restauração

Crie um backup com `./scripts/backup.sh ./backups`. O dump customizado recebe modo `0600`; mova-o para armazenamento cifrado e aplique retenção externa.

Valide sem substituir dados existentes:

```bash
backup=$(./scripts/backup.sh /tmp/shopee-backups)
./scripts/restore-test.sh "$backup"
```

O teste cria um banco temporário dentro do PostgreSQL exclusivo do projeto, restaura, verifica `alembic_version` e remove o banco no final. Para desastre real, pare API/worker, provisione volume limpo, restaure com a credencial administrativa, valide schema e readiness e somente então retome os serviços. Nunca restaure sobre o banco ativo sem backup e janela aprovada.
