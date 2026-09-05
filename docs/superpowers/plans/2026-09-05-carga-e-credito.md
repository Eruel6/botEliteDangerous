# Carga a caminho e crédito de entrega — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o consolidado passa a descontar o que já está no porão de alguém, e a mensagem de cada obra passa a creditar quem entregou.

**Architecture:** o cliente ganha um módulo `comandante.py` que lê o `Cargo.json` e extrai entregas e alvo do Journal, e manda tudo num endpoint novo `POST /comandante`, uma vez por ciclo. O servidor guarda carga (substituída inteira a cada relato) e entregas (deduplicadas por chave natural), e um módulo puro `transito.py` distribui a carga entre as obras.

**Tech Stack:** Python 3.10, FastAPI, discord.py, SQLite (stdlib `sqlite3`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-carga-e-credito-design.md`

## Global Constraints

- Código, comentários, docstrings e mensagens de commit em **português**, indicativo em 3ª pessoa.
- **Pré-requisito:** o plano `2026-09-05-consolidado-esquadrao.md` precisa estar implementado. As tasks 8 e 9 alteram `consolidado.py` e a mensagem de obra.
- Validade da carga: **15 minutos**. Limite da mensagem do Discord: **2000 caracteres**.
- `tests/test_servidor.py` usa a **fixture** `servidor` (linha 13), não `import servidor`. Todo teste que toca o servidor recebe `servidor` por parâmetro e usa `servidor.banco`.
- Rodar com `.venv/bin/python -m pytest`. A suíte inteira verde ao fim de cada task.
- Nada de dependência nova.
- **Premissa a confirmar antes da Task 2:** o formato real do `Cargo.json`. O plano assume `{"Inventory": [{"Name": "...", "Name_Localised": "...", "Count": N, "Stolen": 0}]}`. Se divergir, só a Task 2 muda.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `comandante.py` (novo, cliente) | Lê `Cargo.json`, extrai entregas e alvo do Journal, monta o retrato. |
| `transito.py` (novo, servidor) | A cascata de atribuição. Função pura. |
| `ed_parser.py` | `registros` vira público; `Instalacao` ganha `sistema`; a mensagem de obra ganha o rodapé de crédito. |
| `monitor.py` | Passa a mandar o retrato do comandante uma vez por ciclo. |
| `armazenamento.py` | Tabelas `carga` e `entregas`, coluna `sistema`. |
| `consolidado.py` | Coluna "A caminho". |
| `servidor.py` | Endpoint `/comandante`, crédito no rodapé, reconciliação do crédito. |

---

### Task 1: `registros` público e o sistema da obra

**Files:**
- Modify: `ed_parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Produces: `ed_parser.registros(caminho_log)` (era `_registros`); `Instalacao.sistema: str = ""`; `instalacao_de_payload(nome, materiais, market_id=None, sistema="")`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/fixtures/journal_com_sistema.log` com exatamente estas quatro linhas:

```
{ "timestamp":"2025-05-20T17:00:00Z", "event":"FSDJump", "StarSystem":"Wregoe KP-E c25-11" }
{ "timestamp":"2025-05-20T17:05:00Z", "event":"ApproachSettlement", "MarketID":901, "Name":"Planetary Construction Site: Alfa" }
{ "timestamp":"2025-05-20T17:06:00Z", "event":"ColonisationConstructionDepot", "MarketID":901, "ConstructionProgress":0.1, "ResourcesRequired":[{"Name":"$Steel_name;","Name_Localised":"Aço","RequiredAmount":100,"ProvidedAmount":10}] }
{ "timestamp":"2025-05-20T18:00:00Z", "event":"FSDJump", "StarSystem":"Outro Sistema" }
```

Acrescentar ao fim de `tests/test_parser.py`:

```python
COM_SISTEMA = os.path.join(FIXTURES, "journal_com_sistema.log")


def test_registros_e_publico_e_devolve_os_eventos():
    eventos = [r.get("event") for r in ed_parser.registros(COM_SISTEMA)]

    assert eventos == [
        "FSDJump",
        "ApproachSettlement",
        "ColonisationConstructionDepot",
        "FSDJump",
    ]


def test_a_obra_recebe_o_sistema_corrente():
    """ApproachSettlement não traz StarSystem; o sistema vem do FSDJump anterior."""
    (obra,) = ed_parser.extrair_instalacoes(COM_SISTEMA)

    assert obra.sistema == "Wregoe KP-E c25-11"


def test_o_sistema_e_o_do_momento_da_obra_nao_o_ultimo_do_log():
    """O log termina em outro sistema; a obra continua no sistema onde foi vista."""
    (obra,) = ed_parser.extrair_instalacoes(COM_SISTEMA)

    assert obra.sistema != "Outro Sistema"


def test_instalacao_de_payload_aceita_sistema():
    inst = ed_parser.instalacao_de_payload("X", [], market_id=1, sistema="Sol")

    assert inst.sistema == "Sol"


def test_instalacao_de_payload_sem_sistema_fica_vazia():
    inst = ed_parser.instalacao_de_payload("X", [], market_id=1)

    assert inst.sistema == ""
```

Se `FIXTURES` ou `ed_parser` ainda não estiverem definidos no topo de
`tests/test_parser.py`, acrescentar o que faltar.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_parser.py -v -k "registros or sistema"`
Expected: FAIL com `AttributeError: module 'ed_parser' has no attribute 'registros'`

- [ ] **Step 3: Implementar o mínimo**

Em `ed_parser.py`:

Renomear `_registros` para `registros` (a docstring nova explica por que é público):

```python
def registros(caminho_log):
    """Cada linha do Journal como dicionário; linhas inválidas são puladas.

    Público porque o comandante.py precisa do mesmo fluxo — dois parsers do
    mesmo arquivo seria uma divergência esperando para acontecer.
    """
    with open(caminho_log, "r", encoding="utf-8") as f:
        for linha in f:
            try:
                yield json.loads(linha)
            except json.JSONDecodeError:
                continue
```

Atualizar as duas chamadas internas (`extrair_instalacoes` e
`sinais_de_construcao`) de `_registros(` para `registros(`.

Acrescentar o campo ao dataclass `Instalacao`, depois de `falhou`:

```python
    sistema: str = ""
```

Em `extrair_instalacoes`, iniciar o rastreio antes do laço:

```python
    sistema_corrente = ""
```

e, logo depois de `evento = registro.get("event")`, antes da cadeia de `if`:

```python
        # Qualquer evento que carregue StarSystem serve: FSDJump, Location,
        # Docked, SupercruiseExit. Rastrear o corrente cobre a obra planetária,
        # que é aproximada sem pouso e cujo ApproachSettlement não traz sistema.
        if registro.get("StarSystem"):
            sistema_corrente = registro["StarSystem"]
```

No ramo do `ColonisationConstructionDepot`, logo depois de `instalacao._ordem = ordem`:

```python
            instalacao.sistema = sistema_corrente
```

E `instalacao_de_payload` ganha o parâmetro:

```python
def instalacao_de_payload(nome, materiais, market_id=None, sistema=""):
```

passando `sistema=sistema` na construção do `Instalacao` que ela devolve.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add ed_parser.py tests/test_parser.py tests/fixtures/journal_com_sistema.log
git commit -m "Carimba o sistema corrente na obra e publica registros"
```

---

### Task 2: Ler o `Cargo.json`

**Files:**
- Create: `comandante.py`
- Test: `tests/test_comandante.py`

**Interfaces:**
- Produces: `NOME_ARQUIVO_CARGO = "Cargo.json"`, `ler_cargo_json(pasta=None) -> dict`.

**Antes de começar:** conferir o formato real do `Cargo.json` numa máquina com o
jogo. Se divergir do assumido aqui, ajustar só esta task.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_comandante.py`:

```python
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import comandante


def _escrever(pasta, conteudo):
    caminho = os.path.join(str(pasta), comandante.NOME_ARQUIVO_CARGO)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return str(pasta)


def test_cargo_json_valido_vira_dicionario(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({
        "event": "Cargo",
        "Vessel": "Ship",
        "Count": 740,
        "Inventory": [
            {"Name": "aluminium", "Name_Localised": "Alumínio", "Count": 720, "Stolen": 0},
            {"Name": "steel", "Name_Localised": "Aço", "Count": 20, "Stolen": 0},
        ],
    }))

    assert comandante.ler_cargo_json(pasta) == {"Alumínio": 720, "Aço": 20}


def test_usa_o_nome_cru_quando_nao_ha_localizado(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({
        "Inventory": [{"Name": "steel", "Count": 20}]
    }))

    assert comandante.ler_cargo_json(pasta) == {"steel": 20}


def test_arquivo_ausente_devolve_vazio(tmp_path):
    assert comandante.ler_cargo_json(str(tmp_path)) == {}


def test_arquivo_vazio_devolve_vazio(tmp_path):
    assert comandante.ler_cargo_json(_escrever(tmp_path, "")) == {}


def test_arquivo_truncado_no_meio_da_escrita_devolve_vazio(tmp_path):
    """O jogo reescreve esse arquivo enquanto o cliente lê."""
    pasta = _escrever(tmp_path, '{"Inventory": [{"Name": "alumin')

    assert comandante.ler_cargo_json(pasta) == {}


def test_porao_vazio_devolve_vazio(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({"Count": 0, "Inventory": []}))

    assert comandante.ler_cargo_json(pasta) == {}


def test_item_sem_contagem_positiva_e_ignorado(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({
        "Inventory": [
            {"Name_Localised": "Aço", "Count": 0},
            {"Name_Localised": "Ouro", "Count": 5},
        ]
    }))

    assert comandante.ler_cargo_json(pasta) == {"Ouro": 5}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_comandante.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'comandante'`

- [ ] **Step 3: Implementar o mínimo**

Criar `comandante.py`:

```python
"""O retrato do comandante: o que está no porão, o que ele entregou e para onde vai.

Roda no cliente. O Journal responde "o que foi entregue" e "qual a última obra
vista"; o porão detalhado só existe no Cargo.json, que o jogo sobrescreve.
"""

import json
import os
from dataclasses import dataclass, field

import ed_parser

NOME_ARQUIVO_CARGO = "Cargo.json"


def ler_cargo_json(pasta=None):
    """O porão como {material: quantidade}. Dicionário vazio em qualquer falha.

    O jogo reescreve o arquivo enquanto o cliente lê, então uma leitura no meio
    da escrita é esperada e não pode derrubar o ciclo.
    """
    base = os.path.expanduser(pasta or ed_parser.PASTA_JOURNAL_PADRAO)
    caminho = os.path.join(base, NOME_ARQUIVO_CARGO)

    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}

    if not isinstance(dados, dict):
        return {}

    porao = {}
    for item in dados.get("Inventory") or []:
        if not isinstance(item, dict):
            continue
        nome = item.get("Name_Localised") or item.get("Name")
        quantidade = item.get("Count") or 0
        if nome and quantidade > 0:
            porao[nome] = porao.get(nome, 0) + quantidade
    return porao
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_comandante.py -v`
Expected: PASS, 7 testes

- [ ] **Step 5: Commit**

```bash
git add comandante.py tests/test_comandante.py
git commit -m "Lê o porão do Cargo.json sem quebrar em leitura parcial"
```

---

### Task 3: Entregas e alvo

**Files:**
- Modify: `comandante.py`
- Test: `tests/test_comandante.py`

**Interfaces:**
- Consumes: `ed_parser.registros` (Task 1).
- Produces: `Entrega(quando, market_id, material, quantidade)`, `RetratoComandante(carga, alvo_market_id, alvo_sistema, entregas)`, `extrair_entregas(caminho_log) -> list`, `alvo_atual(caminho_log) -> tuple`, `montar_retrato(caminho_log, pasta=None) -> RetratoComandante`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/fixtures/journal_com_entregas.log` com exatamente estas seis linhas:

```
{ "timestamp":"2025-05-20T17:00:00Z", "event":"FSDJump", "StarSystem":"Wregoe KP-E c25-11" }
{ "timestamp":"2025-05-20T17:06:00Z", "event":"ColonisationConstructionDepot", "MarketID":901, "ResourcesRequired":[{"Name":"$Steel_name;","Name_Localised":"Aço","RequiredAmount":100,"ProvidedAmount":10}] }
{ "timestamp":"2025-05-20T17:37:50Z", "event":"ColonisationContribution", "MarketID":901, "Contributions":[{"Name":"$Aluminium_name;","Name_Localised":"Alumínio","Amount":720}] }
{ "timestamp":"2025-05-20T17:40:00Z", "event":"ColonisationContribution", "MarketID":901, "Contributions":[{"Name":"$Steel_name;","Name_Localised":"Aço","Amount":10},{"Name":"$Gold_name;","Name_Localised":"Ouro","Amount":5}] }
{ "timestamp":"2025-05-20T18:00:00Z", "event":"FSDJump", "StarSystem":"Outro Sistema" }
{ "timestamp":"2025-05-20T18:10:00Z", "event":"ColonisationConstructionDepot", "MarketID":902, "ResourcesRequired":[{"Name":"$Gold_name;","Name_Localised":"Ouro","RequiredAmount":50,"ProvidedAmount":0}] }
```

Acrescentar a `tests/test_comandante.py`:

```python
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
COM_ENTREGAS = os.path.join(FIXTURES, "journal_com_entregas.log")
SEM_DEPOT = os.path.join(FIXTURES, "journal_sem_depot.log")


def test_extrai_uma_entrega_por_contribuicao():
    entregas = comandante.extrair_entregas(COM_ENTREGAS)

    assert len(entregas) == 3


def test_um_evento_com_duas_contribuicoes_vira_duas_entregas():
    entregas = comandante.extrair_entregas(COM_ENTREGAS)
    do_segundo_evento = [e for e in entregas if e.quando == "2025-05-20T17:40:00Z"]

    assert sorted(e.material for e in do_segundo_evento) == ["Aço", "Ouro"]


def test_a_entrega_carrega_obra_material_e_quantidade():
    (primeira,) = [e for e in comandante.extrair_entregas(COM_ENTREGAS)
                   if e.material == "Alumínio"]

    assert primeira.market_id == 901
    assert primeira.quantidade == 720
    assert primeira.quando == "2025-05-20T17:37:50Z"


def test_log_sem_contribuicao_devolve_lista_vazia():
    assert comandante.extrair_entregas(SEM_DEPOT) == []


def test_o_alvo_e_a_ultima_obra_vista_com_o_sistema_daquele_momento():
    market_id, sistema = comandante.alvo_atual(COM_ENTREGAS)

    assert market_id == 902
    assert sistema == "Outro Sistema"


def test_log_sem_obra_nenhuma_nao_tem_alvo():
    market_id, sistema = comandante.alvo_atual(SEM_DEPOT)

    assert market_id is None
    assert sistema == ""


def test_montar_retrato_junta_porao_alvo_e_entregas(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({
        "Inventory": [{"Name_Localised": "Alumínio", "Count": 720}]
    }))

    retrato = comandante.montar_retrato(COM_ENTREGAS, pasta=pasta)

    assert retrato.carga == {"Alumínio": 720}
    assert retrato.alvo_market_id == 902
    assert retrato.alvo_sistema == "Outro Sistema"
    assert len(retrato.entregas) == 3
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_comandante.py -v -k "entrega or alvo or retrato"`
Expected: FAIL com `AttributeError: module 'comandante' has no attribute 'extrair_entregas'`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `comandante.py`:

```python
@dataclass(frozen=True)
class Entrega:
    quando: str          # timestamp do evento, como veio do Journal
    market_id: int
    material: str        # nome localizado
    quantidade: int


@dataclass
class RetratoComandante:
    carga: dict = field(default_factory=dict)
    alvo_market_id: int = None
    alvo_sistema: str = ""
    entregas: list = field(default_factory=list)


def extrair_entregas(caminho_log):
    """Uma Entrega por material de cada ColonisationContribution do log.

    O cliente reenvia a sessão inteira a cada ciclo de propósito: o servidor
    deduplica por chave natural, então nada se perde num restart do Render e o
    cliente não precisa guardar estado.
    """
    entregas = []
    for registro in ed_parser.registros(caminho_log):
        if not isinstance(registro, dict):
            continue
        if registro.get("event") != "ColonisationContribution":
            continue
        market_id = registro.get("MarketID")
        quando = registro.get("timestamp")
        if market_id is None or not quando:
            continue
        for contribuicao in registro.get("Contributions") or []:
            if not isinstance(contribuicao, dict):
                continue
            material = contribuicao.get("Name_Localised") or contribuicao.get("Name")
            quantidade = contribuicao.get("Amount") or 0
            if material and quantidade > 0:
                entregas.append(
                    Entrega(
                        quando=quando,
                        market_id=market_id,
                        material=material,
                        quantidade=quantidade,
                    )
                )
    return entregas


def alvo_atual(caminho_log):
    """(market_id, sistema) da última obra vista no log. (None, "") se não houver."""
    market_id = None
    sistema = ""
    corrente = ""
    for registro in ed_parser.registros(caminho_log):
        if not isinstance(registro, dict):
            continue
        if registro.get("StarSystem"):
            corrente = registro["StarSystem"]
        if registro.get("event") == "ColonisationConstructionDepot":
            market_id = registro.get("MarketID")
            sistema = corrente
    return market_id, sistema


def montar_retrato(caminho_log, pasta=None):
    market_id, sistema = alvo_atual(caminho_log)
    return RetratoComandante(
        carga=ler_cargo_json(pasta),
        alvo_market_id=market_id,
        alvo_sistema=sistema,
        entregas=extrair_entregas(caminho_log),
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_comandante.py -v`
Expected: PASS, 14 testes

- [ ] **Step 5: Commit**

```bash
git add comandante.py tests/test_comandante.py tests/fixtures/journal_com_entregas.log
git commit -m "Extrai entregas e obra alvo do Journal"
```

---

### Task 4: A cascata de atribuição

**Files:**
- Create: `transito.py`
- Test: `tests/test_transito.py`

**Interfaces:**
- Consumes: `ed_parser.Instalacao` com o campo `sistema` (Task 1).
- Produces: `atribuir(carga, obras_abertas, alvo_market_id, sistema) -> dict` no formato `{market_id: {material: quantidade}}`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_transito.py`:

```python
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ed_parser
import transito


def _obra(market_id, sistema, faltas):
    """faltas: {material: quanto falta}"""
    return ed_parser.Instalacao(
        market_id=market_id,
        nome=f"Obra {market_id}",
        materiais=[
            ed_parser.Material(nome=m, nome_interno="", requerido=q, fornecido=0)
            for m, q in faltas.items()
        ],
        sistema=sistema,
    )


def test_tudo_cabe_no_alvo():
    obras = [_obra(1, "Sol", {"Aço": 500})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 300}}


def test_o_teto_do_alvo_e_respeitado():
    obras = [_obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_o_excedente_transborda_para_a_que_mais_precisa():
    obras = [
        _obra(1, "Sol", {"Aço": 100}),
        _obra(2, "Sol", {"Aço": 50}),
        _obra(3, "Sol", {"Aço": 400}),
    ]

    resultado = transito.atribuir({"Aço": 300}, obras, 1, "Sol")

    assert resultado == {1: {"Aço": 100}, 3: {"Aço": 200}}


def test_o_transbordo_continua_na_proxima_quando_a_primeira_enche():
    obras = [
        _obra(1, "Sol", {"Aço": 100}),
        _obra(2, "Sol", {"Aço": 50}),
        _obra(3, "Sol", {"Aço": 120}),
    ]

    resultado = transito.atribuir({"Aço": 300}, obras, 1, "Sol")

    assert resultado == {1: {"Aço": 100}, 3: {"Aço": 120}, 2: {"Aço": 50}}


def test_o_que_nao_cabe_em_lugar_nenhum_e_descartado():
    obras = [_obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Aço": 900}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_obra_de_outro_sistema_nao_recebe_transbordo():
    obras = [
        _obra(1, "Sol", {"Aço": 100}),
        _obra(2, "Outro", {"Aço": 500}),
    ]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_obra_sem_sistema_nao_recebe_transbordo():
    """Linha vinda da reconciliação do canal: a mensagem não carrega o sistema."""
    obras = [
        _obra(1, "Sol", {"Aço": 100}),
        _obra(2, "", {"Aço": 500}),
    ]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_material_que_ninguem_precisa_e_ignorado():
    obras = [_obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Ouro": 50}, obras, 1, "Sol") == {}


def test_sem_alvo_vai_direto_para_o_transbordo():
    obras = [
        _obra(1, "Sol", {"Aço": 100}),
        _obra(2, "Sol", {"Aço": 400}),
    ]

    resultado = transito.atribuir({"Aço": 300}, obras, None, "Sol")

    assert resultado == {2: {"Aço": 300}}


def test_alvo_ja_completo_transborda_tudo():
    obras = [
        _obra(1, "Sol", {}),
        _obra(2, "Sol", {"Aço": 400}),
    ]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {2: {"Aço": 300}}


def test_obra_sem_market_id_nao_participa():
    """Duas linhas reconciliadas teriam market_id None e colidiriam na chave."""
    obras = [_obra(None, "Sol", {"Aço": 100}), _obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_transito.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'transito'`

- [ ] **Step 3: Implementar o mínimo**

Criar `transito.py`:

```python
"""Distribui o porão de um comandante entre as obras que ainda precisam do material.

Função pura, sem banco e sem Discord. A regra é do Arthur: tudo vai para a
última obra visitada, o excedente transborda para as outras do mesmo sistema, e
o que sobrar é descartado.
"""


def atribuir(carga, obras_abertas, alvo_market_id, sistema):
    """{market_id: {material: quantidade}} com a carga distribuída."""
    faltas = {}
    sistemas = {}
    for obra in obras_abertas:
        # market_id None vem da reconciliação do canal; duas dessas colidiriam
        # na chave e uma comeria a atribuição da outra.
        if obra.market_id is None:
            continue
        faltas[obra.market_id] = {
            m.nome: m.faltando for m in obra.materiais if m.faltando > 0
        }
        sistemas[obra.market_id] = obra.sistema

    resultado = {}

    def alocar(market_id, material, quantidade):
        cabe = min(quantidade, faltas.get(market_id, {}).get(material, 0))
        if cabe <= 0:
            return 0
        resultado.setdefault(market_id, {})[material] = (
            resultado.setdefault(market_id, {}).get(material, 0) + cabe
        )
        faltas[market_id][material] -= cabe
        return cabe

    for material, quantidade in carga.items():
        restante = quantidade
        if alvo_market_id is not None:
            restante -= alocar(alvo_market_id, material, restante)
        if restante <= 0:
            continue

        outras = [
            market_id
            for market_id, sist in sistemas.items()
            if market_id != alvo_market_id and sist and sist == sistema
        ]
        outras.sort(key=lambda mid: (-faltas.get(mid, {}).get(material, 0), mid))

        for market_id in outras:
            if restante <= 0:
                break
            restante -= alocar(market_id, material, restante)

    return resultado
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_transito.py -v`
Expected: PASS, 11 testes

- [ ] **Step 5: Commit**

```bash
git add transito.py tests/test_transito.py
git commit -m "Distribui a carga entre a obra alvo e as do mesmo sistema"
```

---

### Task 5: As tabelas `carga` e `entregas`

**Files:**
- Modify: `armazenamento.py`
- Test: `tests/test_armazenamento.py`

**Interfaces:**
- Produces: `substituir_carga(quem, itens, alvo, sistema, quando=None)`, `listar_carga(desde=None) -> list[dict]`, `registrar_entregas(quem, entregas) -> int`, `entregas_por_pessoa(market_id) -> dict`. A coluna `sistema` entra em `instalacoes` via `COLUNAS_NOVAS`, e `salvar`/`_para_registro` passam a levá-la.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_armazenamento.py`:

```python
def test_a_obra_guarda_e_devolve_o_sistema(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))
    inst = ed_parser.instalacao_de_payload("Obra", [], market_id=1, sistema="Sol")

    banco.salvar(inst, message_id=1)

    assert banco.obter("Obra").instalacao.sistema == "Sol"


def test_carga_substitui_a_anterior_da_mesma_pessoa(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))

    banco.substituir_carga("Eruel", {"Aço": 100}, alvo=1, sistema="Sol")
    banco.substituir_carga("Eruel", {"Ouro": 50}, alvo=1, sistema="Sol")

    linhas = banco.listar_carga()
    assert len(linhas) == 1
    assert linhas[0]["material"] == "Ouro"


def test_carga_de_outra_pessoa_nao_e_afetada(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))

    banco.substituir_carga("Eruel", {"Aço": 100}, alvo=1, sistema="Sol")
    banco.substituir_carga("btpopov", {"Ouro": 50}, alvo=1, sistema="Sol")
    banco.substituir_carga("Eruel", {"Aço": 200}, alvo=1, sistema="Sol")

    por_pessoa = {l["quem"]: l["quantidade"] for l in banco.listar_carga()}
    assert por_pessoa == {"Eruel": 200, "btpopov": 50}


def test_carga_velha_e_filtrada_pelo_desde(tmp_path):
    import datetime

    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))
    agora = datetime.datetime.now(datetime.timezone.utc)
    ha_uma_hora = agora - datetime.timedelta(hours=1)
    banco.substituir_carga("Antigo", {"Aço": 100}, alvo=1, sistema="Sol", quando=ha_uma_hora)
    banco.substituir_carga("Novo", {"Ouro": 50}, alvo=1, sistema="Sol", quando=agora)

    corte = agora - datetime.timedelta(minutes=15)
    assert [l["quem"] for l in banco.listar_carga(desde=corte)] == ["Novo"]


def test_entregas_reenviadas_nao_duplicam(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))
    entregas = [
        {"quando": "2025-05-20T17:37:50Z", "market_id": 901, "material": "Alumínio", "quantidade": 720}
    ]

    banco.registrar_entregas("Eruel", entregas)
    banco.registrar_entregas("Eruel", entregas)

    assert banco.entregas_por_pessoa(901) == {"Eruel": 720}


def test_entregas_somam_por_pessoa(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))
    banco.registrar_entregas("Eruel", [
        {"quando": "2025-05-20T17:00:00Z", "market_id": 901, "material": "Aço", "quantidade": 100},
        {"quando": "2025-05-20T18:00:00Z", "market_id": 901, "material": "Ouro", "quantidade": 40},
    ])
    banco.registrar_entregas("btpopov", [
        {"quando": "2025-05-20T19:00:00Z", "market_id": 901, "material": "Aço", "quantidade": 70},
    ])

    assert banco.entregas_por_pessoa(901) == {"Eruel": 140, "btpopov": 70}


def test_entregas_de_outra_obra_nao_entram(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))
    banco.registrar_entregas("Eruel", [
        {"quando": "2025-05-20T17:00:00Z", "market_id": 901, "material": "Aço", "quantidade": 100},
        {"quando": "2025-05-20T17:00:00Z", "market_id": 902, "material": "Aço", "quantidade": 999},
    ])

    assert banco.entregas_por_pessoa(901) == {"Eruel": 100}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_armazenamento.py -v -k "sistema or carga or entregas"`
Expected: FAIL — o primeiro em `TypeError: instalacao_de_payload() got an unexpected keyword argument` se a Task 1 não estiver feita, senão em `AttributeError: 'Armazenamento' object has no attribute 'substituir_carga'`

- [ ] **Step 3: Implementar o mínimo**

Em `armazenamento.py`, acrescentar os esquemas logo depois de `ESQUEMA_META`:

```python
ESQUEMA_CARGA = """
CREATE TABLE IF NOT EXISTS carga (
    quem       TEXT    NOT NULL,
    material   TEXT    NOT NULL,
    quantidade INTEGER NOT NULL,
    alvo       INTEGER,
    sistema    TEXT    NOT NULL DEFAULT '',
    quando     TEXT    NOT NULL,
    PRIMARY KEY (quem, material)
)
"""

ESQUEMA_ENTREGAS = """
CREATE TABLE IF NOT EXISTS entregas (
    quando     TEXT    NOT NULL,
    market_id  INTEGER NOT NULL,
    material   TEXT    NOT NULL,
    quem       TEXT    NOT NULL,
    quantidade INTEGER NOT NULL,
    PRIMARY KEY (quando, market_id, material, quem)
)
"""
```

Executá-los no `__init__`, logo depois do `ESQUEMA_META`:

```python
        self._conexao.execute(ESQUEMA_CARGA)
        self._conexao.execute(ESQUEMA_ENTREGAS)
```

Acrescentar a coluna ao dicionário existente:

```python
COLUNAS_NOVAS = {
    "market_id": "INTEGER",
    "reportado_por": "TEXT NOT NULL DEFAULT ''",
    "sistema": "TEXT NOT NULL DEFAULT ''",
}
```

Em `salvar`, incluir `sistema` no INSERT — a lista de colunas passa a terminar
em `, sistema)`, o `VALUES` ganha mais um `?`, o `DO UPDATE SET` ganha
`sistema=excluded.sistema`, e a tupla de parâmetros ganha `instalacao.sistema`
ao final.

Em `_para_registro`, passar o sistema adiante:

```python
            instalacao=ed_parser.instalacao_de_payload(
                linha["nome"],
                json.loads(linha["materiais"]),
                market_id=linha["market_id"] if "market_id" in chaves else None,
                sistema=(linha["sistema"] if "sistema" in chaves else "") or "",
            ),
```

E os quatro métodos novos, depois de `marcar_finalizado`:

```python
    def substituir_carga(self, quem, itens, alvo, sistema, quando=None):
        """Troca o porão inteiro dessa pessoa. Sem delta: o retrato manda."""
        momento = (quando or _agora()).isoformat()
        self._conexao.execute("DELETE FROM carga WHERE quem = ?", (quem,))
        self._conexao.executemany(
            "INSERT INTO carga (quem, material, quantidade, alvo, sistema, quando) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (quem, material, int(quantidade), alvo, sistema, momento)
                for material, quantidade in itens.items()
                if int(quantidade) > 0
            ],
        )
        self._conexao.commit()

    def listar_carga(self, desde=None):
        """Linhas de carga; com ``desde``, só as relatadas a partir daquele momento."""
        sql = "SELECT * FROM carga"
        parametros = ()
        if desde is not None:
            sql += " WHERE quando >= ?"
            parametros = (desde.isoformat(),)
        return [dict(l) for l in self._conexao.execute(sql, parametros)]

    def registrar_entregas(self, quem, entregas):
        """Grava o que ainda não estava lá. Devolve quantas entraram.

        O cliente reenvia a sessão inteira a cada ciclo; a chave primária
        composta é o que torna isso barato em vez de destrutivo.
        """
        antes = self._conexao.total_changes
        self._conexao.executemany(
            "INSERT OR IGNORE INTO entregas "
            "(quando, market_id, material, quem, quantidade) VALUES (?, ?, ?, ?, ?)",
            [
                (e["quando"], e["market_id"], e["material"], quem, int(e["quantidade"]))
                for e in entregas
            ],
        )
        self._conexao.commit()
        return self._conexao.total_changes - antes

    def entregas_por_pessoa(self, market_id):
        """{quem: toneladas entregues} naquela obra."""
        return {
            l["quem"]: l["total"]
            for l in self._conexao.execute(
                "SELECT quem, SUM(quantidade) AS total FROM entregas "
                "WHERE market_id = ? GROUP BY quem",
                (market_id,),
            )
        }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add armazenamento.py tests/test_armazenamento.py
git commit -m "Guarda carga em trânsito e entregas por pessoa"
```

---

### Task 6: O endpoint `POST /comandante`

**Files:**
- Modify: `servidor.py`
- Test: `tests/test_servidor.py`

**Interfaces:**
- Consumes: os quatro métodos da Task 5.
- Produces: rota `POST /comandante`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_servidor.py`:

```python
# --- endpoint do comandante ---------------------------------------------------


PAYLOAD_COMANDANTE = {
    "carga": [{"material": "Alumínio", "quantidade": 720}],
    "alvo": {"market_id": 901, "sistema": "Sol"},
    "entregas": [
        {"quando": "2025-05-20T17:37:50Z", "market_id": 901,
         "material": "Alumínio", "quantidade": 720}
    ],
}


def test_comandante_sem_token_e_401(cliente_http):
    assert cliente_http.post("/comandante", json=PAYLOAD_COMANDANTE).status_code == 401


def test_comandante_grava_carga_e_entregas(servidor_multi_http):
    cliente, mod = servidor_multi_http

    resposta = cliente.post(
        "/comandante", json=PAYLOAD_COMANDANTE, headers={"X-API-Token": "tok-arthur"}
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
    assert [l["material"] for l in mod.banco.listar_carga()] == ["Alumínio"]
    assert mod.banco.entregas_por_pessoa(901) == {"Arthur": 720}


def test_comandante_funciona_com_o_discord_fora_do_ar(servidor_multi_http):
    """O /logdata devolve 503 sem o bot pronto; este endpoint não pode."""
    cliente, _ = servidor_multi_http

    resposta = cliente.post(
        "/comandante", json=PAYLOAD_COMANDANTE, headers={"X-API-Token": "tok-arthur"}
    )

    assert resposta.status_code == 200


def test_comandante_com_carga_invalida_e_400(servidor_multi_http):
    cliente, _ = servidor_multi_http

    resposta = cliente.post(
        "/comandante", json={"carga": "não é lista"}, headers={"X-API-Token": "tok-arthur"}
    )

    assert resposta.status_code == 400
```

Este bloco precisa de uma fixture que dê o cliente HTTP **e** o módulo, com um
token nomeado. Acrescentar junto das outras fixtures do arquivo:

```python
@pytest.fixture
def servidor_multi_http(monkeypatch, tmp_path):
    """TestClient com API_TOKENS nomeado, e o módulo para inspecionar o banco."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-de-teste")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "estado.db"))
    monkeypatch.setenv("API_TOKENS", "Arthur=tok-arthur")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor as mod

    # sem lifespan: não conecta no Discord
    return TestClient(mod.app), mod
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_servidor.py -v -k comandante`
Expected: FAIL com `404` na rota, porque `/comandante` ainda não existe

- [ ] **Step 3: Implementar o mínimo**

Em `servidor.py`, acrescentar a rota logo depois de `receber_dados`:

```python
@app.post("/comandante")
async def receber_comandante(request: Request, x_api_token: str = Header(default=None)):
    """Carga e entregas de uma pessoa. Não depende do Discord.

    O /logdata devolve 503 enquanto o bot não conecta; aqui isso custaria a
    carga do ciclo inteiro por nada, já que este endpoint só escreve no banco.
    """
    quem = conferir_token(x_api_token)

    data = await request.json()
    carga = data.get("carga") or []
    entregas = data.get("entregas") or []
    alvo = data.get("alvo") or {}

    if not isinstance(carga, list) or not isinstance(entregas, list) or not isinstance(alvo, dict):
        raise HTTPException(status_code=400, detail="Dados inválidos.")

    itens = {}
    for item in carga:
        if not isinstance(item, dict):
            continue
        material = item.get("material")
        quantidade = item.get("quantidade") or 0
        if material and quantidade > 0:
            itens[material] = itens.get(material, 0) + int(quantidade)

    banco.substituir_carga(
        quem, itens, alvo=alvo.get("market_id"), sistema=alvo.get("sistema") or ""
    )
    banco.registrar_entregas(
        quem,
        [
            e
            for e in entregas
            if isinstance(e, dict)
            and e.get("quando")
            and e.get("market_id") is not None
            and e.get("material")
            and (e.get("quantidade") or 0) > 0
        ],
    )
    return JSONResponse(content={"status": "ok"})
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add servidor.py tests/test_servidor.py
git commit -m "Recebe carga e entregas num endpoint por pessoa"
```

---

### Task 7: O cliente manda o retrato

**Files:**
- Modify: `monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `comandante.montar_retrato` (Task 3); o endpoint da Task 6.
- Produces: `url_do_comandante(api_url) -> str`, `payload_do_comandante(retrato) -> dict`, `enviar_comandante(retrato, config) -> Resposta`. `sincronizar` ganha o parâmetro `enviar_retrato=enviar_comandante`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_monitor.py`:

```python
def test_a_url_do_comandante_sai_da_url_de_logdata():
    """O config.txt de quem já usa aponta para /logdata; derivar evita mexer nele."""
    assert (
        monitor.url_do_comandante("https://exemplo.onrender.com/logdata")
        == "https://exemplo.onrender.com/comandante"
    )


def test_o_payload_do_comandante_tem_carga_alvo_e_entregas():
    import comandante

    retrato = comandante.RetratoComandante(
        carga={"Alumínio": 720},
        alvo_market_id=901,
        alvo_sistema="Sol",
        entregas=[comandante.Entrega("2025-05-20T17:37:50Z", 901, "Alumínio", 720)],
    )

    payload = monitor.payload_do_comandante(retrato)

    assert payload["carga"] == [{"material": "Alumínio", "quantidade": 720}]
    assert payload["alvo"] == {"market_id": 901, "sistema": "Sol"}
    assert payload["entregas"][0]["quando"] == "2025-05-20T17:37:50Z"


def test_sincronizar_manda_o_retrato_uma_vez_por_ciclo():
    enviados = []
    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO,
        {},
        CONFIG,
        e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: enviados.append(r) or monitor.Resposta(200, ""),
    )

    assert len(enviados) == 1, "uma vez por ciclo, não uma por obra"


def test_falha_no_retrato_nao_derruba_o_ciclo():
    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO,
        {},
        CONFIG,
        e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(500, "explodiu"),
    )

    assert any("comandante" in erro["mensagem"] for erro in e.como_dicionario()["erros"])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_monitor.py -v -k "comandante or retrato"`
Expected: FAIL com `AttributeError: module 'monitor' has no attribute 'url_do_comandante'`

- [ ] **Step 3: Implementar o mínimo**

Em `monitor.py`, acrescentar `import comandante` junto de `import ed_parser`, e:

```python
def url_do_comandante(api_url):
    """Deriva do API_URL em vez de pedir uma linha nova no config.txt.

    Quem já instalou o cliente tem um config.txt apontando para /logdata;
    exigir uma chave nova quebraria essas instalações no dia do deploy.
    """
    return api_url.rsplit("/", 1)[0] + "/comandante"


def payload_do_comandante(retrato):
    return {
        "carga": [
            {"material": material, "quantidade": quantidade}
            for material, quantidade in retrato.carga.items()
        ],
        "alvo": {
            "market_id": retrato.alvo_market_id,
            "sistema": retrato.alvo_sistema,
        },
        "entregas": [
            {
                "quando": e.quando,
                "market_id": e.market_id,
                "material": e.material,
                "quantidade": e.quantidade,
            }
            for e in retrato.entregas
        ],
    }


def enviar_comandante(retrato, config):
    try:
        resp = requests.post(
            url_do_comandante(config.api_url),
            json=payload_do_comandante(retrato),
            headers={"X-API-Token": config.api_token},
            timeout=TIMEOUT_SEGUNDOS,
        )
        return Resposta(resp.status_code, _detalhe_da(resp))
    except Exception as e:
        return Resposta(None, _resumir(f"{type(e).__name__}: {e}"))
```

A assinatura de `sincronizar` ganha o parâmetro novo:

```python
def sincronizar(
    log_path, memoria, config, estado_cliente,
    enviar=enviar_para_api, enviar_retrato=enviar_comandante,
):
```

E, ao fim da função, depois do laço das obras:

```python
    retrato = comandante.montar_retrato(log_path)
    resposta = enviar_retrato(retrato, config)
    if resposta.status is None or not (200 <= resposta.status < 300):
        estado_cliente.registrar_erro(
            _com_detalhe(f"comandante: envio recusado ({resposta.status})", resposta.detalhe)
        )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "Manda o retrato do comandante uma vez por ciclo"
```

---

### Task 8: A coluna "A caminho" no consolidado

**Files:**
- Modify: `consolidado.py`, `servidor.py`
- Test: `tests/test_consolidado.py`, `tests/test_servidor.py`

**Interfaces:**
- Consumes: `transito.atribuir` (Task 4); `listar_carga` (Task 5).
- Produces: `LinhaConsolidada.a_caminho: int = 0`; `consolidar(instalacoes, a_caminho=None)`; `VALIDADE_CARGA_MINUTOS = 15` e `a_caminho_por_material(banco_alvo, obras, agora)` em `servidor.py`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_consolidado.py`:

```python
def test_a_caminho_entra_na_linha_do_material():
    obras = [_obra("A", [_material("Steel", 1000, 0)])]

    retrato = consolidado.consolidar(obras, a_caminho={"Steel": 400})

    assert retrato.linhas[0].faltando == 1000
    assert retrato.linhas[0].a_caminho == 400


def test_sem_carga_a_caminho_a_coluna_nao_aparece():
    retrato = consolidado.consolidar([_obra("A", [_material("Steel", 100, 0)])])

    assert "A caminho" not in consolidado.formatar_consolidado(retrato, QUANDO)


def test_com_carga_a_caminho_a_coluna_aparece():
    retrato = consolidado.consolidar(
        [_obra("A", [_material("Steel", 1000, 0)])], a_caminho={"Steel": 400}
    )

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert "A caminho" in texto
    assert "400" in texto


def test_a_ordenacao_nao_muda_por_causa_da_carga_a_caminho():
    """Ordena por faltando, não por 'faltando menos o que vem' — carga evapora."""
    obras = [_obra("A", [_material("Steel", 1000, 0), _material("Ouro", 900, 0)])]

    retrato = consolidado.consolidar(obras, a_caminho={"Steel": 950})

    assert [l.material for l in retrato.linhas] == ["Steel", "Ouro"]


def test_material_a_caminho_que_ninguem_precisa_e_ignorado():
    obras = [_obra("A", [_material("Steel", 100, 0)])]

    retrato = consolidado.consolidar(obras, a_caminho={"Platina": 500})

    assert [l.material for l in retrato.linhas] == ["Steel"]
```

E a `tests/test_servidor.py`:

```python
def test_a_caminho_ignora_carga_mais_velha_que_a_validade(servidor):
    import datetime

    agora = datetime.datetime.now(datetime.timezone.utc)
    servidor.banco.salvar(
        _obra_de_teste_com_sistema("Obra", 1000, 0, market_id=901, sistema="Sol"),
        message_id=1,
    )
    servidor.banco.substituir_carga(
        "Antigo", {"Steel": 300}, alvo=901, sistema="Sol",
        quando=agora - datetime.timedelta(hours=1),
    )
    servidor.banco.substituir_carga(
        "Novo", {"Steel": 200}, alvo=901, sistema="Sol", quando=agora
    )

    obras = [r.instalacao for r in servidor.banco.listar(pendentes=True)]
    assert servidor.a_caminho_por_material(servidor.banco, obras, agora) == {"Steel": 200}


def _obra_de_teste_com_sistema(nome, requerido, fornecido, market_id, sistema):
    import ed_parser

    return ed_parser.instalacao_de_payload(
        nome,
        [{"Name_Localised": "Steel", "RequiredAmount": requerido, "ProvidedAmount": fornecido}],
        market_id=market_id,
        sistema=sistema,
    )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_consolidado.py tests/test_servidor.py -v -k "a_caminho or caminho"`
Expected: FAIL com `TypeError: consolidar() got an unexpected keyword argument 'a_caminho'`

- [ ] **Step 3: Implementar o mínimo**

Em `consolidado.py`, o dataclass ganha o campo:

```python
@dataclass(frozen=True)
class LinhaConsolidada:
    material: str
    faltando: int
    obras: int
    a_caminho: int = 0
```

`consolidar` ganha o parâmetro e o repassa:

```python
def consolidar(instalacoes, a_caminho=None):
    a_caminho = a_caminho or {}
    ...
    linhas = tuple(
        LinhaConsolidada(
            material=nome,
            faltando=faltando,
            obras=quantas,
            a_caminho=a_caminho.get(nome, 0),
        )
        for nome, (faltando, quantas) in sorted(
            totais.items(), key=lambda item: (-item[1][0], item[0])
        )
    )
```

Em `formatar_consolidado`, o cabeçalho e as linhas passam a depender de haver
carga viva:

```python
    LARGURA_CAMINHO = 9
    mostrar_caminho = any(l.a_caminho > 0 for l in retrato.linhas)

    topo = f"{'Material':<{LARGURA_MATERIAL}} | {'Faltam':>{LARGURA_FALTAM}} | "
    if mostrar_caminho:
        topo += f"{'A caminho':>{LARGURA_CAMINHO}} | "
    topo += f"{'Obras':>{LARGURA_OBRAS}}"
```

e, na montagem de cada `candidata`, o mesmo condicional:

```python
        candidata = f"{linha.material:<{LARGURA_MATERIAL}} | {linha.faltando:>{LARGURA_FALTAM}} | "
        if mostrar_caminho:
            candidata += f"{linha.a_caminho:>{LARGURA_CAMINHO}} | "
        candidata += f"{linha.obras:>{LARGURA_OBRAS}}"
```

Em `servidor.py`, acrescentar `import transito` e:

```python
VALIDADE_CARGA_MINUTOS = 15


def a_caminho_por_material(banco_alvo, obras, agora):
    """{material: total a caminho}, já limitado pelo que cada obra ainda precisa.

    Carga relatada há mais de VALIDADE_CARGA_MINUTOS é ignorada: quem desloga
    com o porão cheio esconderia material do esquadrão indefinidamente.
    """
    corte = agora - datetime.timedelta(minutes=VALIDADE_CARGA_MINUTOS)
    por_pessoa = {}
    for linha in banco_alvo.listar_carga(desde=corte):
        dados = por_pessoa.setdefault(
            linha["quem"], {"carga": {}, "alvo": linha["alvo"], "sistema": linha["sistema"]}
        )
        dados["carga"][linha["material"]] = linha["quantidade"]

    total = {}
    for dados in por_pessoa.values():
        atribuido = transito.atribuir(
            dados["carga"], obras, dados["alvo"], dados["sistema"]
        )
        for materiais in atribuido.values():
            for material, quantidade in materiais.items():
                total[material] = total.get(material, 0) + quantidade
    return total
```

E `retrato_atual` passa a alimentar a coluna:

```python
def retrato_atual(banco_alvo, agora=None):
    """Consolidado do que está aberto agora, direto do banco."""
    obras = [r.instalacao for r in banco_alvo.listar(pendentes=True)]
    momento = agora or datetime.datetime.now(datetime.timezone.utc)
    return consolidado.consolidar(
        obras, a_caminho=a_caminho_por_material(banco_alvo, obras, momento)
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add consolidado.py servidor.py tests/test_consolidado.py tests/test_servidor.py
git commit -m "Mostra no consolidado o que já está a caminho"
```

---

### Task 9: O rodapé de crédito

**Files:**
- Modify: `ed_parser.py`, `servidor.py`
- Test: `tests/test_parser.py`, `tests/test_servidor.py`

**Interfaces:**
- Consumes: `entregas_por_pessoa` (Task 5).
- Produces: `formatar_creditos(por_pessoa, limite=...) -> str`, `creditos_na_mensagem(conteudo) -> dict`; `formatar_mensagem_discord(..., creditos=None)`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_parser.py`:

```python
def test_credito_ordena_do_maior_para_o_menor():
    assert ed_parser.formatar_creditos({"btpopov": 720, "Eruel": 1440}) == (
        "entregue: Eruel 1440t · btpopov 720t"
    )


def test_sem_entrega_nao_ha_linha_de_credito():
    assert ed_parser.formatar_creditos({}) == ""


def test_credito_corta_no_limite_e_resume():
    muitos = {f"Piloto{i:02d}": 100 - i for i in range(40)}

    linha = ed_parser.formatar_creditos(muitos, limite=120)

    assert len(linha) <= 140
    assert "+" in linha.rsplit("·", 1)[-1]


def test_a_mensagem_de_obra_carrega_o_credito():
    inst = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}]
    )

    texto = ed_parser.formatar_mensagem_discord(
        inst, "40.0%", rodape="atualizado por Eruel", creditos={"Eruel": 1440}
    )

    assert "-# entregue: Eruel 1440t" in texto


def test_o_credito_nao_e_reconciliado_do_canal(servidor):
    """Reler o rodapé duplicaria: o cliente reenvia a sessão inteira todo ciclo,
    então o total do canal e as entregas reenviadas se somariam."""
    import consolidado  # noqa: F401  (garante que o módulo carrega)

    bot = UsuarioFalso(42)
    inst = ed_parser.instalacao_de_payload(
        "Planetary Construction Site: X",
        [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
    )
    texto = ed_parser.formatar_mensagem_discord(inst, "40.0%", creditos={"Eruel": 1440})
    canal = CanalFalso([MensagemComConteudo(333, texto, bot)], bot=bot)

    asyncio.run(servidor.reconciliar_com_o_canal(canal, autor=bot))

    assert servidor.banco.entregas_por_pessoa(333) == {}
```

O último teste vai em `tests/test_servidor.py`, não em `tests/test_parser.py` —
ele precisa da fixture `servidor` e dos dublês de canal.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_parser.py -v -k credito`
Expected: FAIL com `AttributeError: module 'ed_parser' has no attribute 'formatar_creditos'`

- [ ] **Step 3: Implementar o mínimo**

Em `ed_parser.py`:

```python
LIMITE_LINHA_CREDITO = 300


def formatar_creditos(por_pessoa, limite=LIMITE_LINHA_CREDITO):
    """"entregue: Eruel 1440t · btpopov 720t", cortada no limite."""
    if not por_pessoa:
        return ""

    ordenado = sorted(por_pessoa.items(), key=lambda item: (-item[1], item[0]))
    partes = []
    tamanho = len("entregue: ")
    for quem, total in ordenado:
        pedaco = f"{quem} {total}t"
        adicional = len(pedaco) + (3 if partes else 0)
        if tamanho + adicional > limite:
            break
        partes.append(pedaco)
        tamanho += adicional

    restantes = len(ordenado) - len(partes)
    if restantes:
        partes.append(f"+{restantes}")
    return "entregue: " + " · ".join(partes)


_LINHA_DE_CREDITO = re.compile(r"^-# entregue: (.+)$", re.MULTILINE)
_UM_CREDITO = re.compile(r"^(.+) (\d+)t$")


def creditos_na_mensagem(conteudo):
    """Créditos relidos de uma mensagem já postada. O '+N' final é descartado."""
    achado = _LINHA_DE_CREDITO.search(conteudo or "")
    if not achado:
        return {}
    creditos = {}
    for pedaco in achado.group(1).split(" · "):
        item = _UM_CREDITO.match(pedaco.strip())
        if item:
            creditos[item.group(1)] = int(item.group(2))
    return creditos
```

E `formatar_mensagem_discord` ganha o parâmetro, acrescentando a linha depois do
rodapé existente:

```python
def formatar_mensagem_discord(instalacao, porcentagem=None, rodape=None, creditos=None):
    ...
    if rodape:
        linhas.append(f"-# {rodape}")
    linha_credito = formatar_creditos(creditos or {})
    if linha_credito:
        linhas.append(f"-# {linha_credito}")
    return "\n".join(linhas)
```

Em `servidor.py`, `receber_dados` passa os créditos na hora de montar a mensagem:

```python
    creditos = banco.entregas_por_pessoa(instalacao.market_id) if instalacao.market_id else {}
    msg_formatada = ed_parser.formatar_mensagem_discord(
        instalacao, porcentagem, rodape, creditos=creditos
    )
```

**`reconciliar_com_o_canal` NÃO grava crédito.** A spec original mandava reler o
rodapé do canal para o crédito sobreviver ao restart; isso está errado e foi
corrigido. O cliente reenvia todas as entregas da sessão a cada ciclo, então o
total lido do canal somaria com as entregas reenviadas e o rodapé mostraria o
dobro depois de cada restart no meio de uma sessão.

`creditos_na_mensagem` é implementada mesmo assim: ela é o teste de ida e volta
do formato (o que foi escrito é relido igual), e é a peça que uma reconciliação
futura vai precisar se o crédito ganhar armazenamento persistente.

Consequência aceita: o crédito cobre as entregas que estão no Journal atual de
cada cliente. Um restart do Render no meio da sessão não perde nada — os
clientes reabastecem em até 60 s. Entre sessões, o crédito recomeça.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add ed_parser.py servidor.py tests/test_parser.py tests/test_servidor.py
git commit -m "Credita no rodapé da obra quem entregou"
```

---

## Depois do plano

Três coisas que os testes não provam e precisam de olho no primeiro deploy:

1. **O formato real do `Cargo.json`.** Confirmar antes da Task 2; se divergir, só ela muda.
2. **A carga só aparece no Discord no próximo relato de obra.** É o comportamento desenhado na spec, não um bug — mas parece um, se ninguém souber.
3. **O crédito recomeça entre sessões de jogo.** É consequência do disco efêmero do Render, não bug. Se incomodar, a saída é armazenamento persistente (plano pago), não reconciliação pelo canal — essa duplica.
