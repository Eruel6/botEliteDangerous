# Cliente com painel local e uso pelo esquadrão — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o cliente confiável e observável (painel local de status, envio que retenta) e preparar servidor e cliente para o esquadrão inteiro reportar (token por pessoa, uma mensagem por obra arbitrada pelo relato mais completo).

**Architecture:** O cliente vira um processo com duas tarefas ligadas por um objeto `EstadoCliente`: o monitor só escreve nele, o painel HTTP só lê. O servidor passa a mapear token → nome, a chavear instalações por `MarketID` e a ignorar relatos menos completos, respondendo 200 sem tocar no Discord.

**Tech Stack:** Python 3.10+, stdlib (`http.server`, `threading`, `sqlite3`, `secrets`), `requests`, `python-dotenv`, `discord.py`, FastAPI. Testes com `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-03-cliente-painel-e-esquadrao-design.md`

## Global Constraints

- Rodar os testes com `.venv/bin/python -m pytest tests/ -q`. A suíte inteira fica verde ao fim de cada tarefa. A contagem pode mudar: a Task 3 substitui `tests/test_cliente.py` por `tests/test_monitor.py` de propósito.
- Nenhuma dependência nova. O painel usa `http.server` e `threading` da stdlib.
- O painel liga **apenas** em `127.0.0.1`, nunca `0.0.0.0`, e serve apenas rotas explícitas — nunca um diretório.
- Nenhum segredo em arquivo versionado. `config.txt` e `.env` são ignorados pelo git; exemplos usam placeholders óbvios como `<token-gerado-para-o-fulano>`, jamais um prefixo de token real.
- O cliente roda em **Windows** (jogo e cliente na mesma máquina). O launcher é `.bat`.
- Mensagens de commit em português, no indicativo em 3ª pessoa (o padrão do histórico deste repo: "Lê", "Compara", "Isola"), explicando o porquê.
- Todo texto visível ao usuário em português.

## File Structure

**Criados (cliente):**
- `config_cliente.py` — lê e valida `config.txt`. Uma responsabilidade: transformar arquivo em config válida ou erro claro.
- `estado.py` — `EstadoCliente`, o contrato entre monitor e painel.
- `monitor.py` — o loop: Journal → `ed_parser` → POST. Só escreve no estado.
- `painel.py` — servidor HTTP local. Só lê o estado.
- `painel.html` — a página, servida por `painel.py`.
- `config.exemplo.txt` — modelo para cada pessoa do esquadrão.
- `iniciar.bat` — sobe o cliente e abre o navegador.

**Modificados:**
- `cliente.py` — vira só o ponto de entrada que amarra monitor e painel.
- `ed_parser.py` — rodapé opcional na mensagem; `market_id` em `instalacao_de_payload`.
- `armazenamento.py` — colunas `market_id` e `reportado_por`, com migração.
- `servidor.py` — tokens por pessoa, arbitragem do relato mais completo.
- `README.md` — instruções do zip e da config.

**Testes criados:** `tests/test_config_cliente.py`, `tests/test_estado.py`, `tests/test_monitor.py`, `tests/test_painel.py`
**Testes modificados:** `tests/test_cliente.py`, `tests/test_servidor.py`, `tests/test_armazenamento.py`, `tests/test_parser.py`

---

### Task 1: Config do cliente em `config.txt`

**Files:**
- Create: `config_cliente.py`
- Test: `tests/test_config_cliente.py`

**Interfaces:**
- Consumes: nada.
- Produces: `carregar_config(caminho="config.txt") -> Config`, onde `Config` é uma dataclass com os campos `api_token: str` e `api_url: str`. Levanta `ConfigInvalida(Exception)` com mensagem em português quando o arquivo não existe, está sem `API_TOKEN` ou sem `API_URL`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_config_cliente.py
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import config_cliente


def escrever(tmp_path, conteudo):
    caminho = tmp_path / "config.txt"
    caminho.write_text(conteudo, encoding="utf-8")
    return str(caminho)


def test_le_token_e_url(tmp_path):
    caminho = escrever(tmp_path, "API_TOKEN=abc123\nAPI_URL=https://exemplo/logdata\n")

    config = config_cliente.carregar_config(caminho)

    assert config.api_token == "abc123"
    assert config.api_url == "https://exemplo/logdata"


def test_ignora_comentarios_e_linhas_vazias(tmp_path):
    caminho = escrever(
        tmp_path,
        "# o token que o Arthur te passou\nAPI_TOKEN=abc123\n\nAPI_URL=https://exemplo/logdata\n",
    )

    assert config_cliente.carregar_config(caminho).api_token == "abc123"


def test_arquivo_ausente_explica_o_que_fazer(tmp_path):
    with pytest.raises(config_cliente.ConfigInvalida) as erro:
        config_cliente.carregar_config(str(tmp_path / "nao-existe.txt"))

    assert "config.exemplo.txt" in str(erro.value)


def test_token_ausente_e_erro(tmp_path):
    caminho = escrever(tmp_path, "API_URL=https://exemplo/logdata\n")

    with pytest.raises(config_cliente.ConfigInvalida) as erro:
        config_cliente.carregar_config(caminho)

    assert "API_TOKEN" in str(erro.value)


def test_token_vazio_e_erro(tmp_path):
    caminho = escrever(tmp_path, "API_TOKEN=\nAPI_URL=https://exemplo/logdata\n")

    with pytest.raises(config_cliente.ConfigInvalida):
        config_cliente.carregar_config(caminho)


def test_url_ausente_e_erro(tmp_path):
    caminho = escrever(tmp_path, "API_TOKEN=abc123\n")

    with pytest.raises(config_cliente.ConfigInvalida) as erro:
        config_cliente.carregar_config(caminho)

    assert "API_URL" in str(erro.value)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_config_cliente.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'config_cliente'`

- [ ] **Step 3: Implementar o mínimo**

```python
# config_cliente.py
"""Lê e valida o config.txt que fica ao lado do iniciar.bat."""

import os
from dataclasses import dataclass


class ConfigInvalida(Exception):
    """Config ausente ou incompleta. A mensagem diz o que fazer."""


@dataclass
class Config:
    api_token: str
    api_url: str


def _ler_pares(caminho):
    pares = {}
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            pares[chave.strip()] = valor.strip()
    return pares


def carregar_config(caminho="config.txt"):
    if not os.path.exists(caminho):
        raise ConfigInvalida(
            f"Não encontrei {caminho}. Copie config.exemplo.txt para config.txt "
            "e coloque nele o token que você recebeu."
        )

    pares = _ler_pares(caminho)
    faltando = [c for c in ("API_TOKEN", "API_URL") if not pares.get(c)]
    if faltando:
        raise ConfigInvalida(
            f"Faltou preencher em {caminho}: {', '.join(faltando)}."
        )

    return Config(api_token=pares["API_TOKEN"], api_url=pares["API_URL"])
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_config_cliente.py -q`
Expected: PASS, 6 testes

- [ ] **Step 5: Commit**

```bash
git add config_cliente.py tests/test_config_cliente.py
git commit -m "Lê a config do cliente de config.txt com erro explicativo

O cliente lia .env, que o Explorer do Windows esconde por começar com ponto.
config.txt é editável por qualquer um, e a ausência de token agora para o
cliente com uma mensagem que diz o que fazer, em vez de virar um 401 no
meio do loop que ninguém lê."
```

---

### Task 2: `EstadoCliente`, o contrato entre monitor e painel

**Files:**
- Create: `estado.py`
- Test: `tests/test_estado.py`

**Interfaces:**
- Consumes: nada.
- Produces: classe `EstadoCliente` com os métodos `registrar_leitura(journal, instalacoes)`, `registrar_envio(nome, status_http)`, `registrar_erro(mensagem)` e `como_dicionario() -> dict`. `instalacoes` é uma lista de `ed_parser.Instalacao`. `como_dicionario()` devolve estrutura serializável em JSON, consumida pelo painel na Task 4.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_estado.py
import datetime
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ed_parser
import estado


def instalacao(nome="Planetary Construction Site: X", fornecido=4):
    return ed_parser.instalacao_de_payload(
        nome, [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": fornecido}]
    )


def test_comeca_sem_leitura_nem_envio():
    d = estado.EstadoCliente().como_dicionario()

    assert d["journal_atual"] is None
    assert d["ultimo_envio_ok"] is None
    assert d["instalacoes"] == []
    assert d["erros"] == []


def test_registra_a_leitura_com_as_instalacoes():
    e = estado.EstadoCliente()

    e.registrar_leitura("C:/Journal.01.log", [instalacao(fornecido=4)])
    d = e.como_dicionario()

    assert d["journal_atual"] == "C:/Journal.01.log"
    assert d["ultima_leitura"] is not None
    assert d["instalacoes"] == [
        {
            "nome": "Planetary Construction Site: X",
            "porcentagem": 40.0,
            "materiais_faltando": 1,
            "total_faltando": 6,
        }
    ]


def test_registra_envio_bem_sucedido():
    e = estado.EstadoCliente()

    e.registrar_envio("Obra A", 200)
    d = e.como_dicionario()

    assert d["ultimo_status_http"] == 200
    assert d["ultimo_envio_ok"] is not None


def test_envio_com_erro_nao_conta_como_envio_ok():
    e = estado.EstadoCliente()

    e.registrar_envio("Obra A", 401)
    d = e.como_dicionario()

    assert d["ultimo_status_http"] == 401
    assert d["ultimo_envio_ok"] is None


def test_guarda_os_erros_mais_recentes_primeiro():
    e = estado.EstadoCliente()

    e.registrar_erro("primeiro")
    e.registrar_erro("segundo")

    assert [x["mensagem"] for x in e.como_dicionario()["erros"]] == ["segundo", "primeiro"]


def test_descarta_erros_antigos_alem_do_limite():
    e = estado.EstadoCliente(max_erros=3)

    for i in range(5):
        e.registrar_erro(f"erro {i}")

    assert len(e.como_dicionario()["erros"]) == 3


def test_o_dicionario_e_serializavel_em_json():
    e = estado.EstadoCliente()
    e.registrar_leitura("C:/Journal.01.log", [instalacao()])
    e.registrar_envio("Obra A", 200)
    e.registrar_erro("algo quebrou")

    json.dumps(e.como_dicionario())
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_estado.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'estado'`

- [ ] **Step 3: Implementar o mínimo**

```python
# estado.py
"""Estado vivo do cliente: o monitor escreve, o painel lê."""

import datetime
import threading

MAX_ERROS_PADRAO = 20


def _agora():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(momento):
    return momento.isoformat() if momento else None


class EstadoCliente:
    """Compartilhado entre a thread do monitor e a do painel, então protegido
    por um lock. As escritas são raras (uma por ciclo de 60 s) e as leituras
    também (uma a cada 5 s), então um lock simples basta."""

    def __init__(self, max_erros=MAX_ERROS_PADRAO):
        self._lock = threading.Lock()
        self._max_erros = max_erros
        self._journal_atual = None
        self._ultima_leitura = None
        self._ultimo_envio_ok = None
        self._ultimo_status_http = None
        self._instalacoes = []
        self._erros = []
        self._inicio = _agora()

    def registrar_leitura(self, journal, instalacoes):
        with self._lock:
            self._journal_atual = journal
            self._ultima_leitura = _agora()
            self._instalacoes = [
                {
                    "nome": i.nome,
                    "porcentagem": round(i.porcentagem, 1),
                    "materiais_faltando": sum(1 for m in i.materiais if not m.completo),
                    "total_faltando": sum(m.faltando for m in i.materiais if not m.completo),
                }
                for i in instalacoes
            ]

    def registrar_envio(self, nome, status_http):
        with self._lock:
            self._ultimo_status_http = status_http
            if 200 <= status_http < 300:
                self._ultimo_envio_ok = _agora()

    def registrar_erro(self, mensagem):
        with self._lock:
            self._erros.insert(0, {"quando": _iso(_agora()), "mensagem": str(mensagem)})
            del self._erros[self._max_erros :]

    def como_dicionario(self):
        with self._lock:
            return {
                "journal_atual": self._journal_atual,
                "ultima_leitura": _iso(self._ultima_leitura),
                "ultimo_envio_ok": _iso(self._ultimo_envio_ok),
                "ultimo_status_http": self._ultimo_status_http,
                "instalacoes": list(self._instalacoes),
                "erros": list(self._erros),
                "desde": _iso(self._inicio),
            }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_estado.py -q`
Expected: PASS, 7 testes

- [ ] **Step 5: Commit**

```bash
git add estado.py tests/test_estado.py
git commit -m "Adiciona EstadoCliente, o contrato entre monitor e painel

O monitor só escreve e o painel só lê, então cada um pode ser testado sem o
outro. O lock existe porque os dois vivem em threads diferentes, mesmo com
escrita rara."
```

---

### Task 3: Monitor com retentativa e `market_id` no payload

**Files:**
- Create: `monitor.py`
- Test: `tests/test_monitor.py`
- Delete: `tests/test_cliente.py`

`cliente.py` NÃO é tocado nesta tarefa — ele continua com o código antigo até a
Task 5, que o reescreve. Nada mais importa as funções antigas dele depois que
`tests/test_cliente.py` sai.

**Interfaces:**
- Consumes: `config_cliente.Config` (Task 1), `estado.EstadoCliente` (Task 2), `ed_parser.extrair_instalacoes`, `ed_parser.encontrar_log_mais_recente`, `ed_parser.NOME_DESCONHECIDO`.
- Produces: `payload_de(instalacao) -> dict` (agora com a chave `market_id`), `enviar_para_api(payload, config) -> int | None` (devolve o status HTTP, ou `None` quando a requisição nem chegou a acontecer), `sincronizar(log_path, memoria, config, estado_cliente, enviar=enviar_para_api) -> None`, `rodar(config, estado_cliente, intervalo=60) -> None` (o loop infinito).

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_monitor.py
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import config_cliente
import ed_parser
import estado
import monitor

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BASICO = os.path.join(FIXTURES, "journal_basico.log")

CONFIG = config_cliente.Config(api_token="tok", api_url="https://exemplo/logdata")


def test_payload_inclui_o_market_id():
    (inst, _) = ed_parser.extrair_instalacoes(BASICO)

    payload = monitor.payload_de(inst)

    assert payload["market_id"] == 4251780355
    assert payload["instalacao"] == "Planetary Construction Site: Pedder's Forge"


def test_envio_que_falha_e_reenviado_no_ciclo_seguinte():
    tentativas = []

    def enviar_falhando(payload, config):
        tentativas.append(payload["instalacao"])
        return 500

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_falhando)
    quantas_na_primeira = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_falhando)

    assert len(tentativas) == quantas_na_primeira * 2, "deveria ter reenviado tudo"


def test_envio_bem_sucedido_nao_e_reenviado():
    tentativas = []

    def enviar_ok(payload, config):
        tentativas.append(payload["instalacao"])
        return 200

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ok)
    quantas = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ok)

    assert len(tentativas) == quantas, "não deveria ter reenviado nada"


def test_relato_ignorado_pelo_servidor_conta_como_sucesso():
    """200 com status 'ignorado' significa que o servidor recebeu e decidiu.
    Reenviar seria um loop inútil."""
    tentativas = []

    def enviar_ignorado(payload, config):
        tentativas.append(payload["instalacao"])
        return 200

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ignorado)
    quantas = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ignorado)

    assert len(tentativas) == quantas


def test_registra_a_leitura_no_estado():
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e, enviar=lambda p, c: 200)

    d = e.como_dicionario()
    assert d["journal_atual"] == BASICO
    assert len(d["instalacoes"]) == 2


def test_registra_erro_no_estado_quando_o_envio_falha():
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e, enviar=lambda p, c: 401)

    erros = e.como_dicionario()["erros"]
    assert erros, "um 401 deveria virar erro visível"
    assert "401" in erros[0]["mensagem"]


def test_ignora_instalacao_desconhecida():
    enviados = []
    monitor.sincronizar(
        os.path.join(FIXTURES, "journal_sem_fonte_de_nome.log"),
        {},
        CONFIG,
        estado.EstadoCliente(),
        enviar=lambda p, c: enviados.append(p) or 200,
    )

    assert enviados == []


def test_manda_o_token_e_a_url_da_config(monkeypatch):
    capturado = {}

    def post_falso(url, json=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["headers"] = headers

        class R:
            status_code = 200
            text = "ok"

        return R()

    monkeypatch.setattr(monitor.requests, "post", post_falso)

    monitor.enviar_para_api({"instalacao": "X"}, CONFIG)

    assert capturado["url"] == "https://exemplo/logdata"
    assert capturado["headers"]["X-API-Token"] == "tok"


def test_falha_de_rede_devolve_none(monkeypatch):
    def post_explodindo(*args, **kwargs):
        raise OSError("rede caiu")

    monkeypatch.setattr(monitor.requests, "post", post_explodindo)

    assert monitor.enviar_para_api({"instalacao": "X"}, CONFIG) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_monitor.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'monitor'`

- [ ] **Step 3: Implementar o mínimo**

```python
# monitor.py
"""O loop do cliente: lê o Journal e envia as instalações que mudaram."""

import json
import time

import requests

import ed_parser

INTERVALO_CHECAGEM = 60
TIMEOUT_SEGUNDOS = 30


def payload_de(instalacao):
    return {
        "instalacao": instalacao.nome,
        "market_id": instalacao.market_id,
        "materiais": [
            {
                "Name_Localised": m.nome,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in instalacao.materiais
        ],
    }


def enviar_para_api(payload, config):
    """Status HTTP da resposta, ou None se a requisição nem aconteceu."""
    try:
        resp = requests.post(
            config.api_url,
            json=payload,
            headers={"X-API-Token": config.api_token},
            timeout=TIMEOUT_SEGUNDOS,
        )
        return resp.status_code
    except Exception:
        return None


def sincronizar(log_path, memoria, config, estado_cliente, enviar=enviar_para_api):
    """Envia cada instalação cujo estado mudou e ainda não foi aceita.

    A assinatura só é gravada depois de um envio bem-sucedido, então um envio
    que falhou é naturalmente refeito no ciclo seguinte.
    """
    instalacoes = ed_parser.extrair_instalacoes(log_path)
    estado_cliente.registrar_leitura(log_path, instalacoes)

    for instalacao in instalacoes:
        if instalacao.nome == ed_parser.NOME_DESCONHECIDO or not instalacao.materiais:
            continue

        payload = payload_de(instalacao)
        assinatura = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if memoria.get(instalacao.nome) == assinatura:
            continue

        status = enviar(payload, config)
        estado_cliente.registrar_envio(instalacao.nome, status or 0)

        if status is not None and 200 <= status < 300:
            memoria[instalacao.nome] = assinatura
        elif status is None:
            estado_cliente.registrar_erro(f"{instalacao.nome}: falha de rede ao enviar")
        else:
            estado_cliente.registrar_erro(f"{instalacao.nome}: servidor respondeu {status}")


def rodar(config, estado_cliente, intervalo=INTERVALO_CHECAGEM):
    memoria = {}
    while True:
        log_path = ed_parser.encontrar_log_mais_recente()
        if log_path:
            try:
                sincronizar(log_path, memoria, config, estado_cliente)
            except Exception as e:
                estado_cliente.registrar_erro(f"erro ao processar o log: {e}")
        else:
            estado_cliente.registrar_erro("Nenhum Journal encontrado na pasta do jogo.")
        time.sleep(intervalo)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_monitor.py -q`
Expected: PASS, 9 testes

- [ ] **Step 5: Apagar `tests/test_cliente.py`**

O arquivo testava as funções que agora vivem em `monitor.py`, com assinaturas antigas (`sincronizar(log, memoria, enviar=)` sem config nem estado). `tests/test_monitor.py` cobre tudo o que ele cobria, mais a retentativa. Manter os dois seria manter um teste que testa código que não existe mais.

```bash
git rm tests/test_cliente.py
```

- [ ] **Step 6: Rodar a suíte inteira**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. `cliente.py` ainda existe com o código antigo, e nada mais o importa nos testes.

- [ ] **Step 7: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "Extrai o loop para monitor.py e retenta envio que falhou

sincronizar gravava a assinatura do payload mesmo quando o POST falhava,
porque enviar_para_api engolia a exceção e não devolvia nada. Uma queda de
rede custava a atualização até os materiais mudarem de novo. Agora a
assinatura só é gravada depois de um 2xx, então o próprio ciclo de 60 s é a
retentativa.

O payload passou a levar market_id, que o servidor vai usar como chave para
decidir entre relatos de pessoas diferentes."
```

---

### Task 4: Painel HTTP local

**Files:**
- Create: `painel.py`, `painel.html`
- Test: `tests/test_painel.py`

**Interfaces:**
- Consumes: `estado.EstadoCliente` (Task 2).
- Produces: `iniciar_painel(estado_cliente, porta=8765) -> (servidor, porta)`. Sobe um `ThreadingHTTPServer` numa thread daemon ligado em `127.0.0.1` e devolve o objeto e a porta efetivamente usada. `servidor.shutdown()` encerra.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_painel.py
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import estado
import painel


@pytest.fixture
def servidor_no_ar():
    e = estado.EstadoCliente()
    e.registrar_envio("Obra A", 200)
    servidor, porta = painel.iniciar_painel(e, porta=0)
    yield f"http://127.0.0.1:{porta}", e
    servidor.shutdown()


def buscar(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode("utf-8")


def test_estado_json_devolve_o_estado_do_cliente(servidor_no_ar):
    base, _ = servidor_no_ar

    status, corpo = buscar(f"{base}/estado.json")

    assert status == 200
    assert json.loads(corpo)["ultimo_status_http"] == 200


def test_raiz_devolve_a_pagina(servidor_no_ar):
    base, _ = servidor_no_ar

    status, corpo = buscar(f"{base}/")

    assert status == 200
    assert "<html" in corpo.lower()


def test_nao_serve_o_arquivo_de_config(servidor_no_ar):
    """Regressão de segurança: servir o diretório exporia o token de quem roda."""
    base, _ = servidor_no_ar

    for caminho in ("/config.txt", "/../config.txt", "/painel.py"):
        with pytest.raises(urllib.error.HTTPError) as erro:
            buscar(f"{base}{caminho}")
        assert erro.value.code == 404


def test_liga_apenas_em_localhost(servidor_no_ar):
    _, _ = servidor_no_ar
    servidor, porta = painel.iniciar_painel(estado.EstadoCliente(), porta=0)
    try:
        assert servidor.server_address[0] == "127.0.0.1"
    finally:
        servidor.shutdown()


def test_escolhe_outra_porta_quando_a_pedida_esta_ocupada():
    primeiro, porta = painel.iniciar_painel(estado.EstadoCliente(), porta=0)
    try:
        segundo, outra_porta = painel.iniciar_painel(estado.EstadoCliente(), porta=porta)
        try:
            assert outra_porta != porta
        finally:
            segundo.shutdown()
    finally:
        primeiro.shutdown()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_painel.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'painel'`

- [ ] **Step 3: Implementar o mínimo**

```python
# painel.py
"""Servidor HTTP local que mostra o estado do cliente.

Só leitura, só em 127.0.0.1, e só duas rotas explícitas — servir o diretório
exporia o config.txt, que tem o token de quem está rodando.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTA_PADRAO = 8765
TENTATIVAS_DE_PORTA = 10
CAMINHO_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "painel.html")


def _criar_handler(estado_cliente):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/estado.json":
                self._responder(
                    200,
                    "application/json; charset=utf-8",
                    json.dumps(estado_cliente.como_dicionario(), ensure_ascii=False),
                )
            elif self.path in ("/", "/index.html"):
                with open(CAMINHO_HTML, encoding="utf-8") as f:
                    self._responder(200, "text/html; charset=utf-8", f.read())
            else:
                self._responder(404, "text/plain; charset=utf-8", "Não encontrado")

        def _responder(self, status, tipo, corpo):
            dados = corpo.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def log_message(self, *args):
            """Silencia o log de acesso: o painel é consultado a cada 5 s e
            encheria o terminal de ruído."""

    return Handler


def iniciar_painel(estado_cliente, porta=PORTA_PADRAO):
    """Sobe o painel numa thread daemon. Devolve (servidor, porta usada)."""
    handler = _criar_handler(estado_cliente)
    ultimo_erro = None

    for tentativa in range(TENTATIVAS_DE_PORTA):
        alvo = 0 if porta == 0 else porta + tentativa
        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", alvo), handler)
        except OSError as e:
            ultimo_erro = e
            continue
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        return servidor, servidor.server_address[1]

    raise OSError(f"Nenhuma porta livre a partir de {porta}: {ultimo_erro}")
```

- [ ] **Step 4: Criar a página**

```html
<!-- painel.html -->
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Cliente Elite Dangerous</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; padding: 24px; background: #14100c; color: #e8dcc8;
         font: 14px/1.5 ui-monospace, Consolas, monospace; }
  h1 { font-size: 18px; margin: 0 0 20px; color: #ff8c1a; }
  .cartoes { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
  .cartao { background: #1e1813; border: 1px solid #3a2f24; border-radius: 6px;
            padding: 12px 16px; min-width: 180px; }
  .rotulo { font-size: 11px; text-transform: uppercase; color: #9a8b76; }
  .valor { font-size: 16px; margin-top: 4px; }
  .ok { color: #6ac46a; } .ruim { color: #e05c5c; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #2b2219; }
  th { color: #9a8b76; font-weight: normal; font-size: 11px; text-transform: uppercase; }
  .erro { color: #e05c5c; }
  .vazio { color: #6b5d4c; font-style: italic; }
</style>
</head>
<body>
<h1>Cliente Elite Dangerous</h1>

<div class="cartoes">
  <div class="cartao"><div class="rotulo">Conexão</div><div class="valor" id="conexao">—</div></div>
  <div class="cartao"><div class="rotulo">Último envio aceito</div><div class="valor" id="envio">—</div></div>
  <div class="cartao"><div class="rotulo">Última leitura</div><div class="valor" id="leitura">—</div></div>
</div>

<div class="cartao" style="margin-bottom:24px">
  <div class="rotulo">Journal em uso</div><div class="valor" id="journal">—</div>
</div>

<h2 style="font-size:13px;color:#9a8b76;text-transform:uppercase">Instalações detectadas</h2>
<table><thead><tr><th>Instalação</th><th>Progresso</th><th>Materiais faltando</th><th>Unidades</th></tr></thead>
<tbody id="instalacoes"></tbody></table>

<h2 style="font-size:13px;color:#9a8b76;text-transform:uppercase">Erros recentes</h2>
<table><thead><tr><th>Quando</th><th>O quê</th></tr></thead><tbody id="erros"></tbody></table>

<script>
const hora = (iso) => iso ? new Date(iso).toLocaleTimeString("pt-BR") : "nunca";

function pintar(d) {
  const status = d.ultimo_status_http;
  const conexao = document.getElementById("conexao");
  if (status === null)      { conexao.textContent = "sem envio ainda"; conexao.className = "valor"; }
  else if (status >= 200 && status < 300) { conexao.textContent = "ok (" + status + ")"; conexao.className = "valor ok"; }
  else                      { conexao.textContent = "erro " + status;  conexao.className = "valor ruim"; }

  document.getElementById("envio").textContent   = hora(d.ultimo_envio_ok);
  document.getElementById("leitura").textContent = hora(d.ultima_leitura);
  document.getElementById("journal").textContent = d.journal_atual || "nenhum encontrado";

  const inst = document.getElementById("instalacoes");
  inst.innerHTML = d.instalacoes.length
    ? d.instalacoes.map(i => `<tr><td>${i.nome}</td><td>${i.porcentagem}%</td>` +
        `<td>${i.materiais_faltando}</td><td>${i.total_faltando}</td></tr>`).join("")
    : `<tr><td colspan="4" class="vazio">nenhuma obra no Journal atual</td></tr>`;

  const erros = document.getElementById("erros");
  erros.innerHTML = d.erros.length
    ? d.erros.map(e => `<tr><td>${hora(e.quando)}</td><td class="erro">${e.mensagem}</td></tr>`).join("")
    : `<tr><td colspan="2" class="vazio">nenhum erro</td></tr>`;
}

async function atualizar() {
  try { pintar(await (await fetch("/estado.json")).json()); }
  catch (e) { document.getElementById("conexao").textContent = "painel sem resposta"; }
}
atualizar();
setInterval(atualizar, 5000);
</script>
</body>
</html>
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_painel.py -q`
Expected: PASS, 5 testes

- [ ] **Step 6: Commit**

```bash
git add painel.py painel.html tests/test_painel.py
git commit -m "Adiciona painel local de status do cliente

Sem ele não dá para saber se o cliente está funcionando sem ler o terminal —
foi assim que um endereço de API errado passou semanas despercebido.

Só duas rotas explícitas e só em 127.0.0.1: servir o diretório exporia o
config.txt com o token de quem está rodando. Há teste garantindo isso."
```

---

### Task 5: Amarrar tudo em `cliente.py`, com `.bat` e config de exemplo

**Files:**
- Modify: `cliente.py` (substitui o conteúdo inteiro)
- Create: `config.exemplo.txt`, `iniciar.bat`
- Modify: `.gitignore` (ignorar `config.txt`)

**Interfaces:**
- Consumes: `config_cliente.carregar_config` (Task 1), `estado.EstadoCliente` (Task 2), `monitor.rodar` (Task 3), `painel.iniciar_painel` (Task 4).
- Produces: `main() -> int` (código de saída: 0 normal, 1 config inválida).

- [ ] **Step 1: Substituir `cliente.py`**

```python
# cliente.py
"""Ponto de entrada do cliente: sobe o painel e roda o monitor."""

import sys
import webbrowser

import config_cliente
import estado
import monitor
import painel


def main():
    try:
        config = config_cliente.carregar_config()
    except config_cliente.ConfigInvalida as e:
        print(f"\n[CONFIGURAÇÃO] {e}\n")
        return 1

    estado_cliente = estado.EstadoCliente()
    _, porta = painel.iniciar_painel(estado_cliente)
    url = f"http://127.0.0.1:{porta}"

    print(f"Painel em {url}")
    print(f"Enviando para {config.api_url}")
    print("Feche esta janela para parar.\n")
    webbrowser.open(url)

    try:
        monitor.rodar(config, estado_cliente)
    except KeyboardInterrupt:
        print("\nEncerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Criar a config de exemplo**

```
# config.exemplo.txt
# Copie este arquivo para config.txt e preencha o API_TOKEN.
# O token é individual: peça o seu para quem administra o bot.

API_TOKEN=<cole-aqui-o-token-que-voce-recebeu>
API_URL=https://botelitedangerous.onrender.com/logdata
```

- [ ] **Step 3: Criar o launcher**

```bat
@echo off
REM iniciar.bat - sobe o cliente e abre o painel no navegador.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale em https://python.org
    echo Marque "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

if not exist config.txt (
    echo Falta o config.txt.
    echo Copie config.exemplo.txt para config.txt e coloque seu token nele.
    pause
    exit /b 1
)

python -m pip install --quiet --disable-pip-version-check requests
python cliente.py
pause
```

- [ ] **Step 4: Ignorar o `config.txt`**

```bash
printf 'config.txt\n' >> .gitignore
```

- [ ] **Step 5: Verificar que a config ausente para o cliente com mensagem clara**

Run: `cd /tmp && /home/arthur/Documentos/Estudos/botEliteDangerous/.venv/bin/python -c "import sys; sys.path.insert(0,'/home/arthur/Documentos/Estudos/botEliteDangerous'); import cliente; print('saida:', cliente.main())"`
Expected: imprime `[CONFIGURAÇÃO] Não encontrei config.txt. Copie config.exemplo.txt...` e `saida: 1`

- [ ] **Step 6: Rodar a suíte inteira**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add cliente.py config.exemplo.txt iniciar.bat .gitignore
git commit -m "Transforma o cliente em ponto de entrada com painel e launcher

cliente.py agora só amarra config, painel e monitor. O iniciar.bat cobre o
caminho de quem só quer jogar: confere se o Python existe, se o config.txt
foi preenchido, e abre o painel no navegador.

Config faltando encerra com mensagem em vez de entrar no loop e falhar em
silêncio a cada 60 segundos."
```

---

### Task 6: Rodapé de crédito e `market_id` no `ed_parser`

**Files:**
- Modify: `ed_parser.py` (`instalacao_de_payload`, `formatar_mensagem_discord`)
- Modify: `tests/test_parser.py` (acrescentar testes ao fim)

**Interfaces:**
- Consumes: nada novo.
- Produces: `instalacao_de_payload(nome, materiais, market_id=None) -> Instalacao` e `formatar_mensagem_discord(instalacao, porcentagem=None, rodape=None) -> str`. Quando `rodape` é dado, vira uma última linha `-# <rodape>` (o `-#` é a marcação de subtexto do Discord, que renderiza menor e apagado).

- [ ] **Step 1: Escrever os testes que falham**

````python
# acrescentar ao fim de tests/test_parser.py


def test_instalacao_de_payload_aceita_market_id():
    inst = ed.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
        market_id=4251780355,
    )

    assert inst.market_id == 4251780355


def test_instalacao_de_payload_sem_market_id_continua_none():
    inst = ed.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}]
    )

    assert inst.market_id is None


def test_rodape_vira_subtexto_na_ultima_linha():
    a, _ = ed.extrair_instalacoes(BASICO)

    msg = ed.formatar_mensagem_discord(a, porcentagem="40.0%", rodape="atualizado por Fulano às 14:32")

    assert msg.splitlines()[-1] == "-# atualizado por Fulano às 14:32"


def test_sem_rodape_a_mensagem_nao_ganha_linha_extra():
    a, _ = ed.extrair_instalacoes(BASICO)

    assert ed.formatar_mensagem_discord(a).splitlines()[-1] == "```"


def test_rodape_nao_atrapalha_a_releitura_da_mensagem():
    """A reconciliação relê as próprias mensagens; o rodapé não pode virar material."""
    a, _ = ed.extrair_instalacoes(BASICO)
    msg = ed.formatar_mensagem_discord(a, porcentagem="40.0%", rodape="atualizado por Fulano às 14:32")

    assert ed.nome_na_mensagem(msg) == a.nome
    assert len(ed.materiais_na_mensagem(msg)) == len(a.materiais)
````

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_parser.py -q`
Expected: FAIL — `instalacao_de_payload() got an unexpected keyword argument 'market_id'`

- [ ] **Step 3: Implementar**

Em `ed_parser.py`, trocar `instalacao_de_payload` por:

```python
def instalacao_de_payload(nome, materiais, market_id=None):
    """Monta uma ``Instalacao`` a partir do JSON recebido pela API."""
    return Instalacao(
        market_id=market_id,
        nome=nome,
        materiais=[_material(m) for m in materiais],
    )
```

E, em `formatar_mensagem_discord`, trocar a assinatura e o fim da função:

````python
def formatar_mensagem_discord(instalacao, porcentagem=None, rodape=None):
    """Bloco de código para o Discord. ``porcentagem`` e ``rodape`` são opcionais."""
    sufixo = f" `{porcentagem}`" if porcentagem is not None else ""
    linhas = [f"📍 **Materiais para instalação:** `{instalacao.nome}`{sufixo}\n"]
    linhas.append("```")
    linhas.append(f"{'Material':<25} | {'Req.':>5} | {'Fornec.':>7} | {'Faltam':>6}")
    linhas.append("-" * 52)
    for m in instalacao.materiais:
        linhas.append(f"{m.nome:<25} | {m.requerido:>5} | {m.fornecido:>7} | {m.faltando:>6}")
    linhas.append("```")
    if rodape:
        # -# é a marcação de subtexto do Discord: menor e apagado.
        linhas.append(f"-# {rodape}")
    return "\n".join(linhas)
````

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. Os testes de paridade continuam verdes porque eles chamam `formatar_mensagem_discord(instalacao)` sem rodapé, e o formato sem rodapé não mudou.

- [ ] **Step 5: Commit**

```bash
git add ed_parser.py tests/test_parser.py
git commit -m "Aceita market_id no payload e rodapé opcional na mensagem

O market_id vem do cliente e vai ser a chave do servidor para decidir entre
relatos de pessoas diferentes. O rodapé usa a marcação -# do Discord, que
renderiza como subtexto, e fica fora do bloco de código para não ser lido
como material na reconciliação."
```

---

### Task 7: Tokens por pessoa no servidor

**Files:**
- Modify: `servidor.py` (constante `API_TOKEN` e função `conferir_token`)
- Modify: `tests/test_servidor.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `carregar_tokens() -> dict[str, str]` mapeando token → nome, lida de `API_TOKENS` (uma linha `nome=token` por pessoa) e de `API_TOKEN` (compatibilidade, vira `{token: "desconhecido"}`). `conferir_token(token) -> str` devolve o nome de quem enviou; levanta `HTTPException` 401 se o token não bate, 503 se nenhum token está configurado.

- [ ] **Step 1: Escrever os testes que falham**

```python
# acrescentar ao fim de tests/test_servidor.py


def test_carrega_um_token_por_pessoa(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.setenv("API_TOKENS", "Arthur=aaa\nFulano=bbb\n")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    assert servidor.carregar_tokens() == {"aaa": "Arthur", "bbb": "Fulano"}


def test_api_token_sozinho_continua_valendo(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.delenv("API_TOKENS", raising=False)
    monkeypatch.setenv("API_TOKEN", "sozinho")
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    assert servidor.carregar_tokens() == {"sozinho": "desconhecido"}


@pytest.fixture
def servidor_multi(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.setenv("API_TOKENS", "Arthur=aaa\nFulano=bbb\n")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    return servidor


def test_token_conhecido_devolve_o_nome(servidor_multi):
    assert servidor_multi.conferir_token("bbb") == "Fulano"


def test_token_desconhecido_e_401(servidor_multi):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as erro:
        servidor_multi.conferir_token("chute")

    assert erro.value.status_code == 401


def test_sem_nenhum_token_configurado_e_503(monkeypatch, tmp_path):
    from fastapi import HTTPException

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.delenv("API_TOKENS", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    with pytest.raises(HTTPException) as erro:
        servidor.conferir_token("qualquer")

    assert erro.value.status_code == 503
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_servidor.py -q`
Expected: FAIL com `AttributeError: module 'servidor' has no attribute 'carregar_tokens'`

- [ ] **Step 3: Implementar**

Em `servidor.py`, acrescentar `import secrets` no topo, trocar a constante e a função:

```python
API_TOKENS_BRUTO = os.getenv("API_TOKENS", "")
API_TOKEN = os.getenv("API_TOKEN")


def carregar_tokens():
    """Mapa token -> nome de quem reporta.

    API_TOKENS traz uma linha "nome=token" por pessoa. API_TOKEN sozinho
    continua valendo como uma entrada sem nome, para o deploy atual não
    quebrar durante a transição.
    """
    tokens = {}
    for linha in API_TOKENS_BRUTO.splitlines():
        linha = linha.strip()
        if not linha or "=" not in linha:
            continue
        nome, token = linha.split("=", 1)
        if token.strip():
            tokens[token.strip()] = nome.strip()
    if API_TOKEN:
        tokens.setdefault(API_TOKEN, "desconhecido")
    return tokens


def conferir_token(token):
    """Nome de quem enviou. 401 se o token não bate, 503 se não há nenhum."""
    tokens = carregar_tokens()
    if not tokens:
        raise HTTPException(
            status_code=503,
            detail="Servidor sem API_TOKENS configurado; endpoint desabilitado.",
        )
    for conhecido, nome in tokens.items():
        # compare_digest para o tempo de resposta não revelar quanto do token
        # está correto.
        if secrets.compare_digest(token or "", conhecido):
            return nome
    raise HTTPException(status_code=401, detail="Token inválido.")
```

- [ ] **Step 4: Ajustar o teste antigo do endpoint desabilitado**

O teste `test_endpoint_desabilitado_quando_API_TOKEN_nao_esta_configurado` só apaga `API_TOKEN`. Agora precisa apagar `API_TOKENS` também, senão o ambiente pode ter as duas. Acrescentar a linha:

```python
    monkeypatch.delenv("API_TOKENS", raising=False)
```

logo depois do `monkeypatch.delenv("API_TOKEN", raising=False)` existente.

- [ ] **Step 5: Rodar a suíte inteira**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add servidor.py tests/test_servidor.py
git commit -m "Aceita um token por pessoa no servidor

Com o esquadrão rodando o cliente, um token compartilhado significaria
trocar de todo mundo quando um vazasse, e não saber quem reportou o quê.
API_TOKENS traz uma linha nome=token por pessoa; API_TOKEN sozinho continua
valendo para o deploy atual não quebrar na transição.

A comparação usa compare_digest para o tempo de resposta não entregar
quanto do token está certo."
```

---

### Task 8: `market_id` e `reportado_por` no armazenamento

**Files:**
- Modify: `armazenamento.py`
- Modify: `tests/test_armazenamento.py`

**Interfaces:**
- Consumes: `ed_parser.instalacao_de_payload(nome, materiais, market_id)` (Task 6).
- Produces: `Registro` ganha o campo `reportado_por: str`. `Armazenamento.salvar(instalacao, message_id, quando=None, reportado_por="")` e `Armazenamento.obter(chave)` — `chave` pode ser o nome ou o `market_id`; procura primeiro por `market_id`, depois por nome.

- [ ] **Step 1: Escrever os testes que falham**

```python
# acrescentar ao fim de tests/test_armazenamento.py


def instalacao_com_market(market_id=4251780355, nome="Obra A", fornecido=4):
    inst = ed_parser.instalacao_de_payload(
        nome, [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": fornecido}],
        market_id=market_id,
    )
    return inst


def test_guarda_e_recupera_por_market_id(banco):
    banco.salvar(instalacao_com_market(), message_id=9, reportado_por="Arthur")

    registro = banco.obter(4251780355)

    assert registro.message_id == 9
    assert registro.reportado_por == "Arthur"
    assert registro.instalacao.market_id == 4251780355


def test_ainda_recupera_por_nome(banco):
    banco.salvar(instalacao_com_market(nome="Obra A"), message_id=9)

    assert banco.obter("Obra A").message_id == 9


def test_salvar_de_novo_com_o_mesmo_market_id_substitui(banco):
    banco.salvar(instalacao_com_market(fornecido=4), message_id=1)
    banco.salvar(instalacao_com_market(fornecido=9), message_id=2)

    assert banco.obter(4251780355).message_id == 2
    assert len(banco.listar()) == 1


def test_reportado_por_vazio_quando_nao_informado(banco):
    banco.salvar(instalacao_com_market(), message_id=1)

    assert banco.obter(4251780355).reportado_por == ""


def test_migra_banco_antigo_sem_as_colunas_novas(tmp_path):
    """Já existe banco em produção sem market_id nem reportado_por."""
    import sqlite3

    caminho = str(tmp_path / "antigo.db")
    conexao = sqlite3.connect(caminho)
    conexao.execute(
        "CREATE TABLE instalacoes (nome TEXT PRIMARY KEY, message_id INTEGER NOT NULL, "
        "materiais TEXT NOT NULL, ultima_atualizacao TEXT NOT NULL, "
        "finalizado INTEGER NOT NULL DEFAULT 0)"
    )
    conexao.execute(
        "INSERT INTO instalacoes VALUES (?, ?, ?, ?, 0)",
        ("Obra Antiga", 77, '[{"Name_Localised":"Aço","RequiredAmount":10,"ProvidedAmount":2}]',
         "2026-09-03T12:00:00+00:00"),
    )
    conexao.commit()
    conexao.close()

    banco = arm.Armazenamento(caminho)

    registro = banco.obter("Obra Antiga")
    assert registro.message_id == 77, "o dado antigo não pode ser perdido"
    assert registro.reportado_por == ""
    assert registro.instalacao.market_id is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_armazenamento.py -q`
Expected: FAIL — `salvar() got an unexpected keyword argument 'reportado_por'`

- [ ] **Step 3: Implementar**

Em `armazenamento.py`, acrescentar o campo ao `Registro`:

```python
@dataclass
class Registro:
    instalacao: ed_parser.Instalacao
    message_id: int
    ultima_atualizacao: datetime.datetime
    finalizado: bool
    reportado_por: str = ""
```

Acrescentar a migração e trocar `__init__`, `salvar`, `obter` e `_para_registro`:

```python
COLUNAS_NOVAS = {
    "market_id": "INTEGER",
    "reportado_por": "TEXT NOT NULL DEFAULT ''",
}


class Armazenamento:
    def __init__(self, caminho=None):
        # A env é lida aqui, não no import: o servidor define CAMINHO_DB
        # depois que este módulo já foi carregado.
        self.caminho = caminho or os.getenv("CAMINHO_DB", CAMINHO_PADRAO)
        self._conexao = sqlite3.connect(self.caminho)
        self._conexao.row_factory = sqlite3.Row
        self._conexao.execute(ESQUEMA)
        self._migrar()
        self._conexao.commit()

    def _migrar(self):
        """Acrescenta colunas que faltam, sem recriar a tabela.

        Já existe banco em produção; recriar perderia o que está lá."""
        existentes = {
            l["name"] for l in self._conexao.execute("PRAGMA table_info(instalacoes)")
        }
        for coluna, tipo in COLUNAS_NOVAS.items():
            if coluna not in existentes:
                self._conexao.execute(
                    f"ALTER TABLE instalacoes ADD COLUMN {coluna} {tipo}"
                )

    def salvar(self, instalacao, message_id, quando=None, reportado_por=""):
        materiais = [
            {
                "Name_Localised": m.nome,
                "Name": m.nome_interno,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in instalacao.materiais
        ]
        self._conexao.execute(
            "INSERT INTO instalacoes "
            "(nome, message_id, materiais, ultima_atualizacao, finalizado, market_id, reportado_por) "
            "VALUES (?, ?, ?, ?, 0, ?, ?) "
            "ON CONFLICT(nome) DO UPDATE SET "
            "message_id=excluded.message_id, materiais=excluded.materiais, "
            "ultima_atualizacao=excluded.ultima_atualizacao, finalizado=0, "
            "market_id=excluded.market_id, reportado_por=excluded.reportado_por",
            (
                instalacao.nome,
                message_id,
                json.dumps(materiais, ensure_ascii=False),
                (quando or _agora()).isoformat(),
                instalacao.market_id,
                reportado_por,
            ),
        )
        self._conexao.commit()

    def obter(self, chave):
        """Procura por market_id quando ``chave`` é número, senão por nome."""
        if isinstance(chave, int):
            linha = self._conexao.execute(
                "SELECT * FROM instalacoes WHERE market_id = ?", (chave,)
            ).fetchone()
            if linha:
                return self._para_registro(linha)
            return None

        linha = self._conexao.execute(
            "SELECT * FROM instalacoes WHERE nome = ?", (chave,)
        ).fetchone()
        return self._para_registro(linha) if linha else None

    @staticmethod
    def _para_registro(linha):
        chaves = linha.keys()
        return Registro(
            instalacao=ed_parser.instalacao_de_payload(
                linha["nome"],
                json.loads(linha["materiais"]),
                market_id=linha["market_id"] if "market_id" in chaves else None,
            ),
            message_id=linha["message_id"],
            ultima_atualizacao=datetime.datetime.fromisoformat(linha["ultima_atualizacao"]),
            finalizado=bool(linha["finalizado"]),
            reportado_por=(linha["reportado_por"] if "reportado_por" in chaves else "") or "",
        )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. A reconciliação (`servidor.reconciliar_com_o_canal`) chama `banco.salvar(instalacao, message_id=...)` sem `reportado_por`, e o default cobre.

- [ ] **Step 5: Commit**

```bash
git add armazenamento.py tests/test_armazenamento.py
git commit -m "Guarda market_id e quem reportou cada instalação

O market_id é a chave exata para o servidor decidir entre relatos de pessoas
diferentes; o nome sozinho confundiria obras parecidas.

A migração usa ALTER TABLE guardado por PRAGMA table_info em vez de recriar
a tabela, porque já existe banco em produção e recriar perderia o estado
reconstruído do canal."
```

---

### Task 9: Arbitragem do relato mais completo no `/logdata`

**Files:**
- Modify: `servidor.py` (`receber_dados`)
- Modify: `tests/test_servidor.py`

**Interfaces:**
- Consumes: `conferir_token` (Task 7), `Armazenamento.salvar/obter` (Task 8), `ed_parser.instalacao_de_payload` e `formatar_mensagem_discord` (Task 6).
- Produces: `total_fornecido(instalacao) -> int`. `/logdata` passa a responder `{"status": "ok"}` quando postou e `{"status": "ignorado"}` quando o relato não era mais completo que o guardado.

- [ ] **Step 1: Escrever os testes que falham**

```python
# acrescentar ao fim de tests/test_servidor.py


def test_total_fornecido_soma_os_materiais(servidor):
    import ed_parser

    inst = ed_parser.instalacao_de_payload(
        "Obra",
        [
            {"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4},
            {"Name_Localised": "Alumínio", "RequiredAmount": 20, "ProvidedAmount": 6},
        ],
    )

    assert servidor.total_fornecido(inst) == 10


def test_relato_menos_completo_e_ignorado(servidor):
    import ed_parser

    guardado = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 8}],
        market_id=555,
    )
    servidor.banco.salvar(guardado, message_id=1, reportado_por="Arthur")

    chegando = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 3}],
        market_id=555,
    )

    assert servidor.deve_publicar(chegando) is False


def test_relato_mais_completo_e_publicado(servidor):
    import ed_parser

    guardado = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 3}],
        market_id=555,
    )
    servidor.banco.salvar(guardado, message_id=1)

    chegando = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 8}],
        market_id=555,
    )

    assert servidor.deve_publicar(chegando) is True


def test_relato_igual_e_ignorado(servidor):
    import ed_parser

    inst = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 5}],
        market_id=555,
    )
    servidor.banco.salvar(inst, message_id=1)

    assert servidor.deve_publicar(inst) is False


def test_instalacao_nova_sempre_publica(servidor):
    import ed_parser

    inst = ed_parser.instalacao_de_payload(
        "Obra Nunca Vista", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 0}],
        market_id=999,
    )

    assert servidor.deve_publicar(inst) is True
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_servidor.py -q`
Expected: FAIL com `AttributeError: module 'servidor' has no attribute 'total_fornecido'`

- [ ] **Step 3: Implementar**

Em `servidor.py`, acrescentar antes de `receber_dados`:

```python
def total_fornecido(instalacao):
    return sum(m.fornecido for m in instalacao.materiais)


def deve_publicar(instalacao):
    """Só publica relato estritamente mais completo que o guardado.

    O total fornecido só cresce ao longo de uma construção, então "maior
    total" é uma aproximação segura de "mais recente". Isso é o que impede
    N clientes reportando a mesma obra de virarem N apaga-e-reposta por
    minuto no canal.
    """
    chave = instalacao.market_id if instalacao.market_id is not None else instalacao.nome
    anterior = banco.obter(chave)
    if anterior is None:
        return True
    return total_fornecido(instalacao) > total_fornecido(anterior.instalacao)
```

E substituir o corpo de `receber_dados` por:

```python
@app.post("/logdata")
async def receber_dados(request: Request, x_api_token: str = Header(default=None)):
    quem = conferir_token(x_api_token)

    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Bot do Discord ainda não está pronto.")

    data = await request.json()
    nome_instalacao = data.get("instalacao")
    materiais = data.get("materiais")

    if not nome_instalacao or not isinstance(materiais, list):
        raise HTTPException(status_code=400, detail="Dados inválidos.")

    instalacao = ed_parser.instalacao_de_payload(
        nome_instalacao, materiais, market_id=data.get("market_id")
    )

    if not deve_publicar(instalacao):
        return JSONResponse(content={"status": "ignorado"})

    porcentagem = f"{instalacao.porcentagem:.1f}%"
    agora = datetime.datetime.now(datetime.timezone.utc)
    rodape = f"atualizado por {quem} às {agora.strftime('%H:%M')} UTC"
    msg_formatada = ed_parser.formatar_mensagem_discord(instalacao, porcentagem, rodape)

    canal = client.get_channel(DISCORD_CHANNEL_ID)

    # O Discord não deixa editar mensagem antiga do jeito que precisamos aqui,
    # então a anterior é apagada e uma nova é postada no lugar.
    chave = instalacao.market_id if instalacao.market_id is not None else instalacao.nome
    anterior = banco.obter(chave)
    if anterior is not None:
        mensagem_antiga = await buscar_mensagem(canal, anterior.message_id)
        if mensagem_antiga is not None:
            try:
                await mensagem_antiga.delete()
            except Exception as e:
                print(f"Erro ao deletar mensagem anterior: {e}")

    nova_msg = await canal.send(msg_formatada)
    banco.salvar(instalacao, message_id=nova_msg.id, reportado_por=quem)
    await adicionar_reacao_check(nova_msg, instalacao.materiais)

    return JSONResponse(content={"status": "ok"})
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add servidor.py tests/test_servidor.py
git commit -m "Publica só o relato mais completo de cada obra

Com o esquadrão inteiro reportando, cinco clientes vendo a mesma obra
virariam cinco apaga-e-reposta por minuto na mesma mensagem, e o Discord
limita isso. Agora o servidor compara o total fornecido com o que já tem e
responde 200 ignorado sem tocar no canal quando o relato não acrescenta.

A mensagem ganhou um rodapé dizendo quem atualizou e quando, que é o que
responde 'esse dado está fresco?' sem abrir o log do servidor."
```

---

### Task 10: Documentar o zip e a config no README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: tudo das tarefas anteriores.
- Produces: nada de código.

- [ ] **Step 1: Acrescentar as seções ao `README.md`**

Substituir a seção `## Configuração` existente por:

````markdown
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
````

- [ ] **Step 2: Conferir que o README não tem token real**

Run: `grep -nE "[A-Za-z0-9_-]{40,}" README.md`
Expected: nenhuma saída

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Documenta a config por pessoa e o zip do esquadrão

Quem recebe o zip não mexe com código, então as instruções assumem isso:
instalar Python marcando Add to PATH, copiar o config de exemplo, dois
cliques no .bat."
```

---

## Verificação final

Depois da Task 10:

- [ ] `.venv/bin/python -m pytest tests/ -q` — todos verdes
- [ ] `git status --short` — nada não commitado além de `.git-orfao-DELETAR`
- [ ] `grep -rnE "[A-Za-z0-9_-]{40,}" --include="*" . | grep -v "\.env\|\.venv\|\.git/"` — sem token
- [ ] Subir o cliente localmente com um `config.txt` de teste e abrir o painel, conferindo que `/config.txt` devolve 404
