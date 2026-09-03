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
| `cliente.py` | Ponto de entrada do cliente: amarra config, painel e monitor. |
| `config_cliente.py` | Lê e valida o `config.txt` do cliente. |
| `estado.py` | Estado vivo do cliente: o monitor escreve, o painel lê. |
| `monitor.py` | O loop do cliente: lê o Journal e envia o que mudou. |
| `painel.py` | Painel HTTP local de status, só leitura, em `127.0.0.1`. |
| `armazenamento.py` | Estado do servidor (instalação → id da mensagem) em SQLite. |
| `servidor.py` | API FastAPI + bot do Discord. É o que roda no Render. |
| `bot_discord_ed.py` | Geração anterior: bot local que lê o Journal apontado por `LOG_FILE`. |
| `bot_discor_ed_windows.py` | Igual, mas descobre sozinho o Journal mais recente. |
| `parserMaterials.py` | Primeira geração: só imprime a tabela no terminal. |

## Configuração

### Servidor (Render)

Variáveis de ambiente no painel do serviço:

```
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
API_TOKENS=Arthur=<token-do-arthur>
           Fulano=<token-do-fulano>
```

`API_TOKENS` traz uma linha `nome=token` por pessoa. O nome aparece no rodapé
da mensagem no Discord. Para revogar alguém, apague a linha dessa pessoa.

Gere cada token com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Cliente (máquina de quem joga)

Um `config.txt` ao lado do `iniciar.bat`:

```
API_TOKEN=<o token dessa pessoa>
API_URL=https://botelitedangerous.onrender.com/logdata
```

O `config.txt` é ignorado pelo git e nunca deve ser compartilhado — é a
credencial individual.

## Distribuindo para o esquadrão

Monte um zip com: `cliente.py`, `monitor.py`, `painel.py`, `painel.html`,
`estado.py`, `config_cliente.py`, `ed_parser.py`, `config.exemplo.txt` e
`iniciar.bat`.

Instruções para quem recebe:

1. Instale o Python de python.org, marcando **"Add Python to PATH"**.
2. Descompacte o zip numa pasta.
3. Copie `config.exemplo.txt` para `config.txt` e cole seu token nele.
4. Dê dois cliques em `iniciar.bat`.

O painel abre sozinho no navegador em `http://127.0.0.1:8765` e mostra se
está conectado, quando foi o último envio aceito, quais obras foram
detectadas e os erros recentes. Enquanto a janela preta estiver aberta, o
cliente está rodando.

## Estado e o disco do Render

O plano gratuito do Render tem [filesystem efêmero][disks] e não permite disco
persistente, então o SQLite é apagado a cada restart ou redeploy. Por isso o bot
**reconstrói o estado a partir do próprio canal** quando conecta: ele lê as
últimas mensagens que postou, tira delas o nome da instalação e a tabela, e
repovoa o banco. Com um disco persistente (plano pago) o SQLite sozinho já basta
e a reconciliação vira apenas uma rede de segurança.

[disks]: https://render.com/docs/disks

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
