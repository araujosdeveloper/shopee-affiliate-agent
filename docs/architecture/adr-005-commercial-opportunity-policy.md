# ADR-005 — Política de oportunidades comerciais

Status: aceito.

A política fixa `commercial-opportunity-v1` exige score `70.00`, produto ativo e disponível, origem compatível, snapshot não futuro com no máximo 60 minutos e vínculos consistentes. O threshold é constante do domínio, não variável de ambiente.

Oportunidades são recomendações internas. Mudar `candidate` para `shortlisted` ou `dismissed` exige ação humana autenticada; expiração é a única transição automática. Nenhuma oportunidade gera link, mensagem ou publicação.
