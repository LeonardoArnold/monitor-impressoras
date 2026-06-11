# Painel de Suprimentos (versão web) — Etapa 1

Monitora o nível de **toner** e **cilindro** das impressoras da rede em uma
página web. O usuário pode **adicionar e remover impressoras** pela própria
tela — serve para qualquer setor da prefeitura.

## Como rodar

1. Instale o **Python** (https://python.org/downloads) marcando *Add Python to PATH*.
2. Dê dois cliques em **`iniciar.bat`**.
   - Na primeira vez ele instala o Flask sozinho.
   - O navegador abre em `http://localhost:5000`.
3. Pronto. Clique em **Atualizar** para reler as impressoras.

Para outras máquinas da rede acessarem: descubra o IP deste PC (`ipconfig`) e
acesse `http://IP-DO-PC:5000` no navegador delas.

## Estrutura do projeto (as 3 camadas)

```
monitor_web/
├── snmp_engine.py      → CAMADA DE DADOS  (fala com as impressoras via SNMP)
├── app.py              → CAMADA DE LÓGICA (servidor Flask + API)
├── templates/
│   └── index.html      → CAMADA DE INTERFACE (a tela no navegador)
├── impressoras.json    → onde a lista de impressoras fica salva
├── requirements.txt    → dependências (só o Flask)
└── iniciar.bat         → liga tudo
```

A coleta (SNMP) acontece **no servidor, invisível**. O navegador só mostra o
painel. Mexer numa camada não quebra as outras.

## A API (para você estudar/expandir)

| Método | Rota                        | O que faz                          |
|--------|-----------------------------|------------------------------------|
| GET    | `/api/impressoras`          | lista as impressoras cadastradas   |
| POST   | `/api/impressoras`          | adiciona `{local, ip}`             |
| DELETE | `/api/impressoras/<ip>`     | remove pelo IP                     |
| GET    | `/api/status`               | consulta o nível de todas ao vivo  |

## Próximas etapas (sugestão)

- **Etapa 2** — Agrupar por setor/unidade e busca por nome.
- **Etapa 3** — Guardar histórico e mostrar gráfico de consumo no tempo.
- **Etapa 4** — Alerta automático (e-mail/notificação) quando o toner cair.
- **Etapa 5** — Login de usuário e publicar num servidor da prefeitura.

> Se algum modelo só informar o toner como "OK" em vez do número, dá para ler
> o valor exato direto da página de manutenção da impressora — fica para uma
> etapa futura.
