# Onde comprar o que falta — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o painel local passa a dizer onde comprar cada material que falta, perto de onde o piloto está.

**Architecture:** dois módulos novos no cliente — `ardent.py` fala com a API pública e filtra, `compras.py` decide o que consultar e faz o cache. O `monitor.py` chama uma vez por ciclo e grava no `EstadoCliente`; o painel lê e desenha. O servidor não é tocado.

**Tech Stack:** Python 3.10, `requests` (já é a única dependência do cliente), pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-onde-comprar-design.md`

## Global Constraints

- Código, comentários, docstrings e mensagens de commit em **português**, indicativo em 3ª pessoa.
- **Nenhuma mudança em `servidor.py`, `armazenamento.py` ou `consolidado.py`.** Se uma task quiser tocar esses arquivos, o desenho está errado.
- Nenhuma dependência nova: `requests` já vem no `iniciar.bat`.
- **Nenhum teste chama a API de verdade.** Todos monkeypatcham `requests.get`. A suíte roda offline.
- Base da API: `https://api.ardent-insight.com/v2`. Raio padrão 50 ly, validade 30 dias, cache 15 min, 3 estações por material.
- Rodar com `.venv/bin/python -m pytest`. Suíte inteira verde ao fim de cada task.
- **Premissa a confirmar:** a tabela nave → pad. Só `type9 = 3` está confirmado, pelo Loadout real. Padrão para nave desconhecida é 1, que não filtra nada.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `ardent.py` (novo) | Conversão de nome, chamada HTTP, filtros, ordenação. |
| `compras.py` (novo) | O que consultar, o cache de 15 min, a montagem do resultado por material. |
| `estado.py` | Guarda as sugestões para o painel ler. |
| `monitor.py` | Chama `compras` uma vez por ciclo. |
| `painel.html` | A seção nova. |

---

### Task 1: Nome do material e a chamada à API

**Files:**
- Create: `ardent.py`
- Test: `tests/test_ardent.py`

**Interfaces:**
- Produces: `BASE`, `RAIO_PADRAO_LY = 50`, `TIMEOUT_SEGUNDOS = 30`, `nome_para_api(nome_interno) -> str`, `Estacao` (dataclass), `consultar(sistema, material, volume_minimo, raio=RAIO_PADRAO_LY) -> list[Estacao] | None`.

`consultar` devolve `None` quando não deu para saber (rede, timeout, 404, JSON
inválido) e `[]` quando a API respondeu que não há nada. Os dois casos são
diferentes no painel: um mantém o resultado anterior, o outro diz "nada por
perto".

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_ardent.py`:

```python
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ardent


class RespostaFalsa:
    def __init__(self, status_code, dados=None, texto=None):
        self.status_code = status_code
        self._dados = dados
        self.text = texto if texto is not None else json.dumps(dados)

    def json(self):
        if self._dados is None:
            raise ValueError("não é JSON")
        return self._dados


UMA_ESTACAO = {
    "commodityName": "aluminium",
    "marketId": 3713691904,
    "stationName": "Nagasaki Terminal",
    "stationType": "Coriolis",
    "systemName": "Wregoe QI-M b48-6",
    "distance": 98,
    "distanceToArrival": 2100.5,
    "maxLandingPadSize": 3,
    "stock": 10039,
    "buyPrice": 127,
    "updatedAt": "2026-09-01T08:41:42.000Z",
}


def test_converte_o_nome_interno_para_o_da_api():
    assert ardent.nome_para_api("$Aluminium_name;") == "aluminium"


def test_converte_nome_sem_sufixo():
    assert ardent.nome_para_api("steel") == "steel"


def test_nome_interno_vazio_nao_e_consultavel():
    """Obra vinda da reconciliação do canal não tem nome interno."""
    assert ardent.nome_para_api("") == ""


def test_consulta_devolve_estacoes(monkeypatch):
    monkeypatch.setattr(
        ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, [UMA_ESTACAO])
    )

    (estacao,) = ardent.consultar("Sol", "aluminium", volume_minimo=100)

    assert estacao.nome == "Nagasaki Terminal"
    assert estacao.sistema == "Wregoe QI-M b48-6"
    assert estacao.distancia_ly == 98
    assert estacao.estoque == 10039
    assert estacao.preco == 127
    assert estacao.carrier is False


def test_reconhece_fleet_carrier(monkeypatch):
    carrier = dict(UMA_ESTACAO, stationType="FleetCarrier")
    monkeypatch.setattr(ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, [carrier]))

    (estacao,) = ardent.consultar("Sol", "aluminium", volume_minimo=100)

    assert estacao.carrier is True


def test_a_consulta_manda_raio_e_volume_minimo(monkeypatch):
    capturado = {}

    def get_falso(url, params=None, timeout=None):
        capturado["url"] = url
        capturado["params"] = params
        return RespostaFalsa(200, [])

    monkeypatch.setattr(ardent.requests, "get", get_falso)

    ardent.consultar("Wregoe KP-E c25-11", "aluminium", volume_minimo=180, raio=50)

    assert "Wregoe%20KP-E%20c25-11" in capturado["url"] or "Wregoe KP-E c25-11" in capturado["url"]
    assert capturado["params"] == {"maxDistance": 50, "minVolume": 180}


def test_lista_vazia_e_resposta_nao_erro(monkeypatch):
    """Commodity desconhecida devolve 200 com []. Isso é 'nada por perto'."""
    monkeypatch.setattr(ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, []))

    assert ardent.consultar("Sol", "naoexiste", volume_minimo=100) == []


def test_sistema_desconhecido_devolve_none(monkeypatch):
    monkeypatch.setattr(
        ardent.requests,
        "get",
        lambda *a, **k: RespostaFalsa(404, {"error": "Not Found", "message": "System not found"}),
    )

    assert ardent.consultar("Nao Existe", "aluminium", volume_minimo=100) is None


def test_timeout_devolve_none(monkeypatch):
    def get_estourando(*a, **k):
        raise OSError("tempo esgotado")

    monkeypatch.setattr(ardent.requests, "get", get_estourando)

    assert ardent.consultar("Sol", "aluminium", volume_minimo=100) is None


def test_json_invalido_devolve_none(monkeypatch):
    monkeypatch.setattr(
        ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, None, texto="<html>")
    )

    assert ardent.consultar("Sol", "aluminium", volume_minimo=100) is None


def test_resposta_que_nao_e_lista_devolve_none(monkeypatch):
    monkeypatch.setattr(ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, {"a": 1}))

    assert ardent.consultar("Sol", "aluminium", volume_minimo=100) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_ardent.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'ardent'`

- [ ] **Step 3: Implementar o mínimo**

Criar `ardent.py`:

```python
"""Consulta o Ardent Insight: onde comprar uma commodity perto de um sistema.

API pública, sem chave e sem SLA. Roda no cliente, nunca no servidor: a pergunta
é "perto de mim", e o que está perto de um piloto não está perto do outro.
"""

import urllib.parse
from dataclasses import dataclass

import requests

BASE = "https://api.ardent-insight.com/v2"
RAIO_PADRAO_LY = 50
TIMEOUT_SEGUNDOS = 30


@dataclass(frozen=True)
class Estacao:
    nome: str
    sistema: str
    distancia_ly: float
    distancia_ls: float
    estoque: int
    preco: int
    pad: int
    carrier: bool
    atualizado_em: str


def nome_para_api(nome_interno):
    """"$Aluminium_name;" vira "aluminium".

    A API só entende inglês. O Name_Localised do Journal está no idioma do jogo
    — em português, no caso do Arthur — e por isso não serve. Obra vinda da
    reconciliação do canal tem nome_interno vazio e devolve "": não consultável.
    """
    limpo = (nome_interno or "").strip().strip("$")
    if limpo.endswith("_name;"):
        limpo = limpo[: -len("_name;")]
    return limpo.lower()


def _para_estacao(bruto):
    return Estacao(
        nome=bruto.get("stationName", "?"),
        sistema=bruto.get("systemName", "?"),
        distancia_ly=bruto.get("distance") or 0,
        distancia_ls=bruto.get("distanceToArrival") or 0,
        estoque=bruto.get("stock") or 0,
        preco=bruto.get("buyPrice") or 0,
        pad=bruto.get("maxLandingPadSize") or 0,
        carrier=bruto.get("stationType") == "FleetCarrier",
        atualizado_em=bruto.get("updatedAt", ""),
    )


def consultar(sistema, material, volume_minimo, raio=RAIO_PADRAO_LY):
    """Estações que vendem ``material`` perto de ``sistema``.

    Devolve None quando não deu para saber (rede, timeout, 404, resposta
    estranha) e [] quando a API respondeu que não há nada. O painel trata os
    dois de forma diferente: um mantém o resultado anterior, o outro diz que
    não há nada por perto.
    """
    url = (
        f"{BASE}/system/name/{urllib.parse.quote(sistema)}"
        f"/commodity/name/{urllib.parse.quote(material)}/nearby/exports"
    )
    try:
        resposta = requests.get(
            url,
            params={"maxDistance": raio, "minVolume": volume_minimo},
            timeout=TIMEOUT_SEGUNDOS,
        )
        if resposta.status_code != 200:
            return None
        dados = resposta.json()
    except Exception:
        return None

    if not isinstance(dados, list):
        return None
    return [_para_estacao(b) for b in dados if isinstance(b, dict)]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_ardent.py -v`
Expected: PASS, 11 testes

- [ ] **Step 5: Commit**

```bash
git add ardent.py tests/test_ardent.py
git commit -m "Consulta o Ardent por onde comprar uma commodity"
```

---

### Task 2: Os filtros e a ordenação

**Files:**
- Modify: `ardent.py`
- Test: `tests/test_ardent.py`

**Interfaces:**
- Consumes: `Estacao` da Task 1.
- Produces: `VALIDADE_DIAS = 30`, `MAXIMO_POR_MATERIAL = 3`, `PAD_POR_NAVE`, `pad_necessario(nave) -> int`, `melhores(estacoes, pad_minimo, agora, quantas=MAXIMO_POR_MATERIAL) -> list[Estacao]`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_ardent.py`:

```python
import datetime

AGORA = datetime.datetime(2026, 9, 5, tzinfo=datetime.timezone.utc)


def _estacao(nome, distancia=10, preco=100, pad=3, dias=1, carrier=False, estoque=9999):
    quando = AGORA - datetime.timedelta(days=dias)
    return ardent.Estacao(
        nome=nome,
        sistema="Sistema",
        distancia_ly=distancia,
        distancia_ls=100,
        estoque=estoque,
        preco=preco,
        pad=pad,
        carrier=carrier,
        atualizado_em=quando.isoformat().replace("+00:00", "Z"),
    )


def test_pad_do_type9_e_grande():
    assert ardent.pad_necessario("type9") == 3


def test_nave_desconhecida_nao_filtra_pad():
    assert ardent.pad_necessario("nave_que_nao_existe") == 1


def test_nave_vazia_nao_filtra_pad():
    assert ardent.pad_necessario("") == 1


def test_estacao_com_pad_pequeno_e_descartada():
    estacoes = [_estacao("Grande", pad=3), _estacao("Media", pad=2)]

    assert [e.nome for e in ardent.melhores(estacoes, pad_minimo=3, agora=AGORA)] == ["Grande"]


def test_pad_minimo_1_nao_descarta_ninguem():
    estacoes = [_estacao("Grande", pad=3), _estacao("Media", pad=2)]

    assert len(ardent.melhores(estacoes, pad_minimo=1, agora=AGORA)) == 2


def test_dado_velho_e_descartado():
    estacoes = [_estacao("Fresca", dias=5), _estacao("Velha", dias=90)]

    assert [e.nome for e in ardent.melhores(estacoes, pad_minimo=1, agora=AGORA)] == ["Fresca"]


def test_data_ilegivel_e_descartada():
    ruim = ardent.Estacao("Ruim", "S", 1, 1, 100, 100, 3, False, "nao é data")

    assert ardent.melhores([ruim], pad_minimo=1, agora=AGORA) == []


def test_ordena_por_distancia_e_desempata_por_preco():
    estacoes = [
        _estacao("Longe", distancia=90, preco=10),
        _estacao("Perto caro", distancia=10, preco=500),
        _estacao("Perto barato", distancia=10, preco=100),
    ]

    nomes = [e.nome for e in ardent.melhores(estacoes, pad_minimo=1, agora=AGORA)]

    assert nomes == ["Perto barato", "Perto caro", "Longe"]


def test_corta_em_tres():
    estacoes = [_estacao(f"E{i}", distancia=i) for i in range(10)]

    assert len(ardent.melhores(estacoes, pad_minimo=1, agora=AGORA)) == 3


def test_fleet_carrier_sobrevive_aos_filtros():
    """O Arthur decidiu manter carrier; ele sai marcado, não excluído."""
    estacoes = [_estacao("Carrier", carrier=True)]

    (resultado,) = ardent.melhores(estacoes, pad_minimo=1, agora=AGORA)

    assert resultado.carrier is True
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_ardent.py -v -k "pad or velho or ordena or corta or carrier or ilegivel"`
Expected: FAIL com `AttributeError: module 'ardent' has no attribute 'pad_necessario'`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `ardent.py` — o `import datetime` vai para o topo:

```python
VALIDADE_DIAS = 30
MAXIMO_POR_MATERIAL = 3

#: Pad exigido por nave: 1 pequeno, 2 médio, 3 grande.
#:
#: Só nave de pad grande ganha alguma coisa com este filtro — nave pequena e
#: média pousa em qualquer lugar. Por isso a tabela lista só as grandes, e
#: qualquer nave ausente cai no padrão 1, que não filtra nada. Filtrar errado
#: esconderia estação boa; não filtrar só deixa passar estação ruim.
#:
#: type9 está confirmado pelo Loadout real do Arthur. O resto é dado a conferir.
PAD_POR_NAVE = {
    "type9": 3,
    "type9_military": 3,
    "type7": 3,
    "anaconda": 3,
    "cutter": 3,
    "federation_corvette": 3,
    "belugaliner": 3,
    "independant_trader": 3,
    "typex_3": 3,
}


def pad_necessario(nave):
    return PAD_POR_NAVE.get((nave or "").lower(), 1)


def _idade_em_dias(atualizado_em, agora):
    """None quando a data não é legível — nesse caso a estação é descartada."""
    try:
        quando = datetime.datetime.fromisoformat(
            (atualizado_em or "").replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=datetime.timezone.utc)
    return (agora - quando).total_seconds() / 86400


def melhores(estacoes, pad_minimo, agora, quantas=MAXIMO_POR_MATERIAL):
    """As melhores estações depois dos filtros de pad e validade.

    Estoque e raio já foram filtrados pela própria API, via minVolume e
    maxDistance — melhor cortar lá do que baixar e descartar aqui.
    """
    servem = []
    for estacao in estacoes:
        if estacao.pad < pad_minimo:
            continue
        idade = _idade_em_dias(estacao.atualizado_em, agora)
        if idade is None or idade > VALIDADE_DIAS:
            continue
        servem.append(estacao)

    servem.sort(key=lambda e: (e.distancia_ly, e.preco, e.nome))
    return servem[:quantas]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_ardent.py -v`
Expected: PASS, 21 testes

- [ ] **Step 5: Commit**

```bash
git add ardent.py tests/test_ardent.py
git commit -m "Filtra por pad e validade e ordena por distância"
```

---

### Task 3: O que consultar e o cache

**Files:**
- Create: `compras.py`
- Test: `tests/test_compras.py`

**Interfaces:**
- Consumes: `ardent` (tasks 1 e 2); `ed_parser.Instalacao`.
- Produces: `VALIDADE_CACHE_MINUTOS = 15`, `FRACAO_MINIMA_DO_PORAO = 0.25`, `SugestaoMaterial`, `Cache`, `Buscador(nave, capacidade)` com `sugestoes(obras, sistema, agora) -> list[SugestaoMaterial]`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_compras.py`:

```python
import datetime
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ardent
import compras
import ed_parser

AGORA = datetime.datetime(2026, 9, 5, 12, 0, tzinfo=datetime.timezone.utc)


def _obra(nome, materiais, sistema="Sol"):
    return ed_parser.Instalacao(
        market_id=1,
        nome=nome,
        materiais=[
            ed_parser.Material(nome=n, nome_interno=i, requerido=r, fornecido=0)
            for n, i, r in materiais
        ],
        sistema=sistema,
    )


def _estacao(nome="Estacao"):
    return ardent.Estacao(
        nome=nome, sistema="Sol", distancia_ly=10, distancia_ls=100,
        estoque=9999, preco=100, pad=3, carrier=False,
        atualizado_em=AGORA.isoformat().replace("+00:00", "Z"),
    )


class ConsultaFalsa:
    def __init__(self, resultado=None):
        self.chamadas = []
        self.resultado = [_estacao()] if resultado is None else resultado

    def __call__(self, sistema, material, volume_minimo, raio=50):
        self.chamadas.append((sistema, material, volume_minimo))
        return self.resultado


def test_consulta_um_material_faltante():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)

    sugestoes = buscador.sugestoes([_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "Sol", AGORA)

    assert [s.material for s in sugestoes] == ["Alumínio"]
    assert consulta.chamadas == [("Sol", "aluminium", 180)]


def test_o_volume_minimo_e_um_quarto_do_porao():
    consulta = ConsultaFalsa()
    compras.Buscador("type9", 720, consultar=consulta).sugestoes(
        [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "Sol", AGORA
    )

    assert consulta.chamadas[0][2] == 180


def test_material_ja_completo_nao_e_consultado():
    consulta = ConsultaFalsa()
    obra = _obra("A", [("Alumínio", "$Aluminium_name;", 100)])
    obra.materiais[0].fornecido = 100

    compras.Buscador("type9", 720, consultar=consulta).sugestoes([obra], "Sol", AGORA)

    assert consulta.chamadas == []


def test_obra_sem_nome_interno_vira_sugestao_nao_consultavel():
    """Linha reconciliada do canal: só o nome localizado sobreviveu."""
    consulta = ConsultaFalsa()

    (sugestao,) = compras.Buscador("type9", 720, consultar=consulta).sugestoes(
        [_obra("A", [("Alumínio", "", 500)])], "Sol", AGORA
    )

    assert sugestao.consultavel is False
    assert sugestao.estacoes == []
    assert consulta.chamadas == []


def test_o_mesmo_material_em_duas_obras_e_uma_consulta_so():
    consulta = ConsultaFalsa()
    obras = [
        _obra("A", [("Alumínio", "$Aluminium_name;", 500)]),
        _obra("B", [("Alumínio", "$Aluminium_name;", 300)]),
    ]

    sugestoes = compras.Buscador("type9", 720, consultar=consulta).sugestoes(obras, "Sol", AGORA)

    assert len(consulta.chamadas) == 1
    assert sugestoes[0].faltando == 800


def test_o_cache_evita_a_segunda_consulta():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=5))

    assert len(consulta.chamadas) == 1


def test_o_cache_vence_depois_de_quinze_minutos():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=16))

    assert len(consulta.chamadas) == 2


def test_mudar_de_sistema_consulta_de_novo():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Outro", AGORA)

    assert [c[0] for c in consulta.chamadas] == ["Sol", "Outro"]


def test_falha_de_rede_mantem_o_ultimo_resultado_bom():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]
    buscador.sugestoes(obras, "Sol", AGORA)

    consulta.resultado = None  # a API sumiu
    depois = buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=16))

    assert [e.nome for e in depois[0].estacoes] == ["Estacao"]
    assert depois[0].desatualizado is True


def test_lista_vazia_nao_e_falha():
    consulta = ConsultaFalsa(resultado=[])
    buscador = compras.Buscador("type9", 720, consultar=consulta)

    (sugestao,) = buscador.sugestoes(
        [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "Sol", AGORA
    )

    assert sugestao.estacoes == []
    assert sugestao.desatualizado is False


def test_sem_sistema_corrente_nao_consulta_nada():
    consulta = ConsultaFalsa()

    sugestoes = compras.Buscador("type9", 720, consultar=consulta).sugestoes(
        [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "", AGORA
    )

    assert consulta.chamadas == []
    assert sugestoes == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_compras.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'compras'`

- [ ] **Step 3: Implementar o mínimo**

Criar `compras.py`:

```python
"""Decide o que consultar no Ardent e guarda o resultado por um tempo.

O preço de uma estação não muda em 60 segundos, que é o ciclo do cliente. Sem
cache, uma dúzia de materiais faltando viraria uma dúzia de requisições por
minuto, por cliente, contra uma API pública e gratuita.
"""

import datetime
from dataclasses import dataclass, field

import ardent

VALIDADE_CACHE_MINUTOS = 15
FRACAO_MINIMA_DO_PORAO = 0.25


@dataclass
class SugestaoMaterial:
    material: str            # nome localizado, que é o que o painel mostra
    faltando: int
    estacoes: list = field(default_factory=list)
    consultavel: bool = True
    desatualizado: bool = False


@dataclass
class _Entrada:
    estacoes: list
    quando: datetime.datetime
    sistema: str


class Buscador:
    """Guarda o cache entre os ciclos. Um por processo de cliente."""

    def __init__(self, nave, capacidade, consultar=ardent.consultar):
        self.nave = nave
        self.capacidade = capacidade
        self._consultar = consultar
        self._cache = {}

    def _volume_minimo(self):
        return int(self.capacidade * FRACAO_MINIMA_DO_PORAO)

    def sugestoes(self, obras, sistema, agora):
        """Uma sugestão por material que ainda falta, com as melhores estações."""
        if not sistema:
            return []

        faltas = {}
        internos = {}
        for obra in obras:
            for material in obra.materiais:
                if material.faltando <= 0:
                    continue
                faltas[material.nome] = faltas.get(material.nome, 0) + material.faltando
                if material.nome_interno:
                    internos[material.nome] = material.nome_interno

        pad = ardent.pad_necessario(self.nave)
        resultado = []

        for nome in sorted(faltas, key=lambda n: (-faltas[n], n)):
            interno = internos.get(nome, "")
            if not interno:
                resultado.append(
                    SugestaoMaterial(material=nome, faltando=faltas[nome], consultavel=False)
                )
                continue

            estacoes, desatualizado = self._buscar(
                ardent.nome_para_api(interno), sistema, agora, pad
            )
            resultado.append(
                SugestaoMaterial(
                    material=nome,
                    faltando=faltas[nome],
                    estacoes=estacoes,
                    desatualizado=desatualizado,
                )
            )
        return resultado

    def _buscar(self, material, sistema, agora, pad):
        """(estações, desatualizado). Mantém o último resultado bom se a API falhar."""
        chave = (material, sistema)
        entrada = self._cache.get(chave)
        limite = datetime.timedelta(minutes=VALIDADE_CACHE_MINUTOS)

        if entrada is not None and agora - entrada.quando < limite:
            return ardent.melhores(entrada.estacoes, pad, agora), False

        cru = self._consultar(sistema, material, self._volume_minimo())
        if cru is None:
            if entrada is None:
                return [], True
            return ardent.melhores(entrada.estacoes, pad, agora), True

        self._cache[chave] = _Entrada(estacoes=cru, quando=agora, sistema=sistema)
        return ardent.melhores(cru, pad, agora), False
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_compras.py -v`
Expected: PASS, 11 testes

- [ ] **Step 5: Commit**

```bash
git add compras.py tests/test_compras.py
git commit -m "Decide o que consultar e guarda o resultado por quinze minutos"
```

---

### Task 4: A nave e o sistema no estado do cliente

**Files:**
- Modify: `estado.py`, `ed_parser.py`
- Test: `tests/test_estado.py`, `tests/test_parser.py`

**Interfaces:**
- Produces: `ed_parser.nave_atual(caminho_log) -> tuple[str, int]`; `EstadoCliente.registrar_compras(sugestoes)`; a chave `compras` em `como_dicionario()`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/fixtures/journal_com_loadout.log` com exatamente estas duas linhas:

```
{ "timestamp":"2025-05-20T17:00:00Z", "event":"Loadout", "Ship":"type9", "ShipName":"FRIEDRICH DER GROSSE", "CargoCapacity":720 }
{ "timestamp":"2025-05-20T17:05:00Z", "event":"FSDJump", "StarSystem":"Sol" }
```

Acrescentar a `tests/test_parser.py`:

```python
COM_LOADOUT = os.path.join(FIXTURES, "journal_com_loadout.log")


def test_a_nave_e_a_capacidade_vem_do_loadout():
    assert ed_parser.nave_atual(COM_LOADOUT) == ("type9", 720)


def test_log_sem_loadout_devolve_nave_vazia():
    assert ed_parser.nave_atual(os.path.join(FIXTURES, "journal_sem_depot.log")) == ("", 0)
```

Acrescentar a `tests/test_estado.py`:

```python
def test_as_compras_entram_no_dicionario():
    e = estado.EstadoCliente()

    e.registrar_compras([
        {"material": "Alumínio", "faltando": 500, "consultavel": True,
         "desatualizado": False, "estacoes": []}
    ])

    assert e.como_dicionario()["compras"][0]["material"] == "Alumínio"


def test_sem_compras_o_dicionario_traz_lista_vazia():
    assert estado.EstadoCliente().como_dicionario()["compras"] == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_parser.py tests/test_estado.py -v -k "nave or compras"`
Expected: FAIL com `AttributeError: module 'ed_parser' has no attribute 'nave_atual'`

- [ ] **Step 3: Implementar o mínimo**

Em `ed_parser.py`:

```python
def nave_atual(caminho_log):
    """(nave, capacidade de carga) do último Loadout. ("", 0) se não houver.

    O Loadout é reescrito a cada troca de nave ou de módulo, então o último do
    log é o que vale.
    """
    nave = ""
    capacidade = 0
    for registro in registros(caminho_log):
        if isinstance(registro, dict) and registro.get("event") == "Loadout":
            nave = registro.get("Ship", "") or ""
            capacidade = registro.get("CargoCapacity", 0) or 0
    return nave, capacidade
```

Em `estado.py`, acrescentar ao `__init__`:

```python
        self._compras = []
```

o método, junto dos outros `registrar_`:

```python
    def registrar_compras(self, sugestoes):
        """Sugestões de compra já prontas para o painel, como dicionários."""
        with self._lock:
            self._compras = list(sugestoes)
```

e a chave em `como_dicionario`, junto de `"erros"`:

```python
                "compras": list(self._compras),
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add ed_parser.py estado.py tests/test_parser.py tests/test_estado.py tests/fixtures/journal_com_loadout.log
git commit -m "Lê a nave do Loadout e guarda as compras no estado"
```

---

### Task 5: O monitor consulta uma vez por ciclo

**Files:**
- Modify: `monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `compras.Buscador` (Task 3); `ed_parser.nave_atual` (Task 4); `comandante.alvo_atual` para o sistema corrente.
- Produces: `sugestao_para_dicionario(sugestao) -> dict`; `sincronizar` ganha `buscador=None`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_monitor.py`:

```python
def test_o_ciclo_grava_as_compras_no_estado():
    import ardent
    import compras

    estacao = ardent.Estacao(
        nome="Nagasaki", sistema="Sol", distancia_ly=10, distancia_ls=100,
        estoque=9999, preco=127, pad=3, carrier=False, atualizado_em="2026-09-01T00:00:00Z",
    )

    class BuscadorFalso:
        def sugestoes(self, obras, sistema, agora):
            return [compras.SugestaoMaterial(material="Alumínio", faltando=500,
                                             estacoes=[estacao])]

    e = estado.EstadoCliente()
    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(200, ""),
        buscador=BuscadorFalso(),
    )

    (sugestao,) = e.como_dicionario()["compras"]
    assert sugestao["material"] == "Alumínio"
    assert sugestao["estacoes"][0]["nome"] == "Nagasaki"
    assert sugestao["estacoes"][0]["carrier"] is False


def test_sem_buscador_o_ciclo_nao_quebra():
    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(200, ""),
        buscador=None,
    )

    assert e.como_dicionario()["compras"] == []


def test_trocar_de_nave_atualiza_o_buscador():
    """Sair de uma nave pequena para o Type-9 muda o pad exigido e o porão."""
    import compras

    buscador = compras.Buscador("sidewinder", 4)
    buscador.nave, buscador.capacidade = "type9", 720

    assert buscador._volume_minimo() == 180


def test_falha_no_buscador_nao_derruba_o_ciclo():
    class BuscadorQueExplode:
        def sugestoes(self, obras, sistema, agora):
            raise RuntimeError("a API sumiu")

    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(200, ""),
        buscador=BuscadorQueExplode(),
    )

    assert any("compra" in erro["mensagem"] for erro in e.como_dicionario()["erros"])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_monitor.py -v -k "compras or buscador"`
Expected: FAIL com `TypeError: sincronizar() got an unexpected keyword argument 'buscador'`

- [ ] **Step 3: Implementar o mínimo**

Em `monitor.py`, acrescentar `import datetime` e `import compras` no topo, e:

```python
def sugestao_para_dicionario(sugestao):
    return {
        "material": sugestao.material,
        "faltando": sugestao.faltando,
        "consultavel": sugestao.consultavel,
        "desatualizado": sugestao.desatualizado,
        "estacoes": [
            {
                "nome": e.nome,
                "sistema": e.sistema,
                "distancia_ly": e.distancia_ly,
                "distancia_ls": e.distancia_ls,
                "estoque": e.estoque,
                "preco": e.preco,
                "carrier": e.carrier,
            }
            for e in sugestao.estacoes
        ],
    }
```

A assinatura de `sincronizar` ganha mais um parâmetro:

```python
def sincronizar(
    log_path, memoria, config, estado_cliente,
    enviar=enviar_para_api, enviar_retrato=enviar_comandante, buscador=None,
):
```

E, ao fim da função, depois do envio do retrato do comandante:

```python
    if buscador is not None:
        try:
            _, sistema = comandante.alvo_atual(log_path)
            agora = datetime.datetime.now(datetime.timezone.utc)
            estado_cliente.registrar_compras(
                [sugestao_para_dicionario(s)
                 for s in buscador.sugestoes(instalacoes, sistema, agora)]
            )
        except Exception as e:
            # A consulta é acessória: o relato das obras não pode parar por causa
            # de uma API de terceiro.
            estado_cliente.registrar_erro(f"compras: {e}")
```

E `rodar` cria o buscador uma vez, fora do laço, para o cache sobreviver entre
ciclos:

```python
def rodar(config, estado_cliente, intervalo=INTERVALO_CHECAGEM):
    memoria = {}
    buscador = None
    while True:
        log_path = ed_parser.encontrar_log_mais_recente()
        if log_path:
            nave, capacidade = ed_parser.nave_atual(log_path)
            if capacidade:
                if buscador is None:
                    buscador = compras.Buscador(nave, capacidade)
                else:
                    # Trocar de nave no meio da sessão muda o pad exigido e o
                    # porão. O cache continua válido: ele guarda a resposta da
                    # API, e os filtros são aplicados na leitura.
                    buscador.nave = nave
                    buscador.capacidade = capacidade
            try:
                sincronizar(log_path, memoria, config, estado_cliente, buscador=buscador)
            except Exception as e:
                estado_cliente.registrar_erro(f"erro ao processar o log: {e}")
        else:
            estado_cliente.registrar_erro("Nenhum Journal encontrado na pasta do jogo.")
        time.sleep(intervalo)
```

O `Buscador` é criado uma vez e atualizado no lugar, em vez de recriado: o cache
de 15 minutos vive nele, e recriar a cada troca de nave jogaria fora consultas
ainda válidas.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "Consulta onde comprar uma vez por ciclo"
```

---

### Task 6: A seção no painel

**Files:**
- Modify: `painel.html`
- Test: `tests/test_painel.py`

**Interfaces:**
- Consumes: a chave `compras` de `como_dicionario()` (Task 4).
- Produces: a seção `#compras` no painel.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_painel.py`:

```python
def test_a_pagina_tem_a_secao_de_compras():
    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()

    assert 'id="compras"' in html
    assert "Onde comprar" in html


def test_a_secao_distingue_falha_de_consulta_de_ausencia_de_resultado():
    """Sem estações porque a API caiu não é o mesmo que sem estações por perto."""
    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()

    assert "não consegui consultar agora" in html
    assert "nada dentro de 50 ly" in html


def test_a_secao_de_compras_usa_textcontent():
    """O nome da estação vem de uma API de terceiro; não pode virar markup."""
    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()

    assert "innerHTML" not in html
```

Se `RAIZ` não estiver definido no topo de `tests/test_painel.py`, acrescentar.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_painel.py -v -k compras`
Expected: FAIL com `assert 'id="compras"' in html`

- [ ] **Step 3: Implementar o mínimo**

Em `painel.html`, acrescentar a seção depois da tabela de instalações e antes da
de erros:

```html
<h2 style="font-size:13px;color:#9a8b76;text-transform:uppercase">Onde comprar</h2>
<div id="compras"></div>
```

E, dentro do `<script>`, no fim de `pintar(d)`:

```js
  const compras = document.getElementById("compras");
  compras.replaceChildren();
  if (!d.compras || !d.compras.length) {
    const vazio = document.createElement("p");
    vazio.className = "vazio";
    vazio.textContent = "nada faltando, ou nenhum sistema conhecido ainda";
    compras.appendChild(vazio);
  }
  for (const s of d.compras || []) {
    const bloco = document.createElement("div");
    bloco.style.marginBottom = "12px";

    const titulo = document.createElement("div");
    titulo.textContent = `${s.material} — falta ${s.faltando}`;
    if (s.desatualizado) titulo.textContent += " (dados antigos)";
    bloco.appendChild(titulo);

    if (!s.consultavel) {
      const nota = document.createElement("div");
      nota.className = "vazio";
      nota.textContent = "sem dados de compra até alguém reportar esta obra de novo";
      bloco.appendChild(nota);
    } else if (!s.estacoes.length) {
      const nota = document.createElement("div");
      nota.className = "vazio";
      // Sem estações e desatualizado não é "não há nada": é "não consegui
      // perguntar". Dizer "nada dentro de 50 ly" aqui seria mentira.
      nota.textContent = s.desatualizado
        ? "não consegui consultar agora"
        : "nada dentro de 50 ly";
      bloco.appendChild(nota);
    }

    for (const e of s.estacoes) {
      const linha = document.createElement("div");
      linha.style.paddingLeft = "16px";
      linha.textContent =
        `${e.carrier ? "🛸 " : ""}${e.nome} · ${e.sistema} · ` +
        `${e.distancia_ly} ly · ${Math.round(e.distancia_ls)} Ls · ` +
        `${e.estoque} t · ${e.preco} cr`;
      bloco.appendChild(linha);
    }
    compras.appendChild(bloco);
  }
```

Tudo via `textContent`: o nome da estação vem de uma API de terceiro alimentada
por jogadores, e o painel já foi corrigido uma vez para não interpolar texto
externo em `innerHTML`.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add painel.html tests/test_painel.py
git commit -m "Mostra no painel onde comprar cada material faltante"
```

---

## Depois do plano

Nenhum teste chama a API de verdade, então a suíte roda offline e não quebra
quando o Ardent estiver fora do ar. Isso deixa duas coisas por conferir à mão,
uma vez, depois de implementar:

1. **A tabela nave → pad.** Só o `type9` está confirmado. O padrão 1 torna um
   erro inofensivo (aparece estação a mais), mas vale conferir as naves que o
   esquadrão realmente voa.
2. **Uma consulta real com o jogo aberto.** O volume da resposta foi de 589
   estações numa medição; vale ver quanto tempo a primeira rajada leva numa
   conexão doméstica ao chegar num sistema novo.
