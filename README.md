# botEliteDangerous

Acompanha a construção de **Planetary Construction Sites** do Elite Dangerous e
publica no Discord uma tabela com os materiais requeridos, fornecidos e faltantes.

## Como funciona

O jogo grava um Journal (JSON-lines) na máquina do jogador. Dois eventos importam:

- `ColonisationConstructionDepot` — traz `MarketID`, o progresso e a lista
  `ResourcesRequired` com os materiais. **Não** traz o nome da instalação.
- `ApproachSettlement` — traz `MarketID` e `Name`.

O `MarketID` é a chave que liga os dois. Toda essa leitura vive em `ed_parser.py`.

## Arquivos

| Arquivo | Papel |
|---|---|
| `ed_parser.py` | Leitura do Journal e formatação das tabelas. Usado por todos os outros. |
| `cliente.py` | Roda no PC do jogador: lê o Journal e faz POST em `/logdata`. |
| `servidor.py` | API FastAPI + bot do Discord. É o que roda no Render. |
| `bot_discord_ed.py` | Geração anterior: bot local que lê o Journal apontado por `LOG_FILE`. |
| `bot_discor_ed_windows.py` | Igual, mas descobre sozinho o Journal mais recente. |
| `parserMaterials.py` | Primeira geração: só imprime a tabela no terminal. |

## Configuração

Crie um `.env` (ele é ignorado pelo git):

```
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
LOG_FILE=...          # usado só por bot_discord_ed.py
API_ADRESS=...        # nome do serviço no Render, sem .onrender.com
```

## Testes

```bash
python3.10 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

Os testes em `tests/test_paridade.py` comparam `ed_parser` com as versões
originais dos scripts (guardadas em `tests/_originais/`) usando Journals reais.
Eles só rodam se houver Journals em `journals/` — essa pasta é ignorada pelo git,
porque os logs são pesados e pessoais. As fixtures pequenas ficam em
`tests/fixtures/` e essas sim são versionadas.
