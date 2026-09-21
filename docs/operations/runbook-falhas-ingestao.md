# Runbook de falhas de ingestão

Para `failed` ou `partially_completed`, confira contagens, linhas rejeitadas e alertas internos. Corrija o arquivo e use nova chave somente se o conteúdo mudar. Não edite snapshots ou scores históricos.

Erros estruturais não criam processamento. Erros permanentes de linha não são repetidos; falhas transitórias usam backoff exponencial, jitter e até quatro tentativas. Preserve batch e auditoria após falha definitiva.
