# Contribuição

Crie uma branch a partir de `main`, mantenha commits pequenos e inclua testes. Código, identificadores e mensagens técnicas são escritos em inglês. Documentação operacional é escrita em português.

Antes de abrir um pull request:

```bash
make validate
docker compose build
docker compose --profile test run --rm test
```

Não use credenciais reais, não habilite publicação automática e não adicione fontes de produto fora de `manual`, `official_import` e `approved_api`.
