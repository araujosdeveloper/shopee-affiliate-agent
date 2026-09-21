# Política de dados

Coletar somente dados necessários à operação afiliada. Não armazenar cookies, credenciais de consumidores, dados de compra pessoal nem material obtido por scraping. Timestamps são UTC; a apresentação comercial pode usar `America/Sao_Paulo`.

Snapshots de preço sempre incluem `collected_at` e não são considerados atuais após 60 minutos. Essa janela é uma política fixa do domínio e do trigger PostgreSQL, sem configuração independente por ambiente. Decisões relevantes são auditadas com motivo e idempotência. Exclusão lógica é usada em cadastros mutáveis; métricas, snapshots e auditoria preservam histórico. Retenção e descarte definitivo serão definidos antes de dados reais.
