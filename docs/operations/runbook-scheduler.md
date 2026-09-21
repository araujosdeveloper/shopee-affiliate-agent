# Runbook do scheduler

O serviço `scheduler` executa Celery Beat sem porta, como usuário não root, filesystem read-only, `cap_drop: ALL`, `no-new-privileges`, 128 MiB e 0,10 CPU. A cada 15 minutos expira oportunidades vencidas e abre alertas de snapshot vencido. Não consulta fonte externa, publica ou envia mensagens.

Mantenha exatamente uma réplica. O pidfile e schedule ficam em `/tmp` da réplica. Não inicie segundo Beat manualmente. As rotinas são idempotentes.
