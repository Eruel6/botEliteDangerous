# Consolidado de materiais do esquadrão — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** publicar no canal do Discord uma mensagem única que soma, por material, tudo que falta em todas as obras abertas do esquadrão.

**Architecture:** um módulo novo `consolidado.py` com três funções puras — agregar, formatar e decidir entre repostar/editar/nada — e o `servidor.py` chamando as três depois de cada relato aceito. O estado da mensagem (id e horário do último repost) vive numa tabela `meta` nova, reconstruída a partir do canal a cada restart, porque o disco do Render é efêmero.

**Tech Stack:** Python 3.10, FastAPI, discord.py, SQLite (stdlib `sqlite3`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-consolidado-esquadrao-design.md`

## Global Constraints

- Código, comentários, docstrings e mensagens de commit em **português**.
- Mensagens de commit no indicativo em 3ª pessoa ("Soma", "Corrige", "Guarda"), como o resto do histórico.
- Limite de mensagem do Discord: **2000 caracteres**.
- Teto da linha de nomes das obras: **300 caracteres**.
- Janela do gatilho temporal: **12 horas**. Cooldown entre reposts: **30 minutos**.
- O cabeçalho da mensagem é exatamente `🧾 **Consolidado do esquadrão**` e não pode casar com `_NOME_NA_MENSAGEM` do `ed_parser`.
- Rodar os testes com `.venv/bin/python -m pytest`. A suíte inteira precisa continuar verde ao fim de cada tarefa (122 testes na linha de base).
- Nada de dependência nova.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `consolidado.py` (novo) | Agregação, formatação e decisão. Três funções puras, sem banco, sem Discord, sem relógio próprio. |
| `tests/test_consolidado.py` (novo) | Cobre o módulo acima. |
| `armazenamento.py` | Ganha a tabela `meta` e o par `obter_meta`/`definir_meta`. |
| `servidor.py` | Corrige o sentido de `finalizado`, reconcilia a mensagem de consolidado e chama o módulo novo depois de cada relato aceito. |

O `ed_parser.py` **não é modificado**: `consolidado.py` importa `MARCA_CONSTRUCAO` dele.

---

### Task 1: O retrato — `consolidar()`

**Files:**
- Create: `consolidado.py`
- Test: `tests/test_consolidado.py`

**Interfaces:**
- Consumes: `ed_parser.Instalacao` e `ed_parser.Material` (já existem).
- Produces: `LinhaConsolidada(material: str, faltando: int, obras: int)`, `Retrato(linhas: tuple, obras: frozenset)`, `consolidar(instalacoes) -> Retrato`.

- [ ] **Step 1: Escrever os testes que falham**

```python
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import consolidado
import ed_parser


def _material(nome, requerido, fornecido, interno=""):
    return ed_parser.Material(
        nome=nome, nome_interno=interno, requerido=requerido, fornecido=fornecido
    )


def _obra(nome, materiais, market_id=None):
    return ed_parser.Instalacao(market_id=market_id, nome=nome, materiais=materiais)


def test_soma_o_mesmo_material_em_obras_diferentes():
    obras = [
        _obra("A", [_material("Steel", 100, 40)]),
        _obra("B", [_material("Steel", 200, 50)]),
    ]

    retrato = consolidado.consolidar(obras)

    assert len(retrato.linhas) == 1
    assert retrato.linhas[0].material == "Steel"
    assert retrato.linhas[0].faltando == 60 + 150
    assert retrato.linhas[0].obras == 2


def test_entrega_a_mais_nao_vira_desconto_em_outra_obra():
    """faltando tem piso em zero por obra: sem isso, 'A' com -50 comeria o de 'B'."""
    obras = [
        _obra("A", [_material("Steel", 100, 150)]),
        _obra("B", [_material("Steel", 100, 40)]),
    ]

    retrato = consolidado.consolidar(obras)

    assert retrato.linhas[0].faltando == 60
    assert retrato.linhas[0].obras == 1, "a obra completa não conta"


def test_agrupa_pelo_nome_localizado_ignorando_o_interno():
    """As linhas vindas da reconciliação do canal têm nome_interno vazio."""
    obras = [
        _obra("A", [_material("Steel", 100, 0, interno="steel")]),
        _obra("B", [_material("Steel", 100, 0, interno="")]),
    ]

    retrato = consolidado.consolidar(obras)

    assert len(retrato.linhas) == 1
    assert retrato.linhas[0].faltando == 200


def test_obra_completa_nao_entra_no_retrato():
    obras = [
        _obra("Pronta", [_material("Steel", 100, 100)]),
        _obra("Aberta", [_material("Steel", 100, 10)]),
    ]

    retrato = consolidado.consolidar(obras)

    assert retrato.obras == frozenset({"Aberta"})


def test_ordena_decrescente_com_desempate_por_nome():
    obras = [
        _obra("A", [
            _material("Zinco", 100, 0),
            _material("Alumínio", 100, 0),
            _material("Steel", 500, 0),
        ])
    ]

    retrato = consolidado.consolidar(obras)

    assert [l.material for l in retrato.linhas] == ["Steel", "Alumínio", "Zinco"]


def test_retratos_iguais_comparam_iguais():
    """decidir_acao compara dois retratos com ==; isso precisa valer."""
    obras = [_obra("A", [_material("Steel", 100, 0)])]

    assert consolidado.consolidar(obras) == consolidado.consolidar(obras)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_consolidado.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'consolidado'`

- [ ] **Step 3: Implementar o mínimo**

Criar `consolidado.py`:

```python
"""Soma, por material, o que falta em todas as obras abertas do esquadrão.

Três funções puras: agregar, formatar e decidir o que fazer com a mensagem.
Nenhuma delas toca banco, Discord ou relógio — quem tem esses é o servidor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LinhaConsolidada:
    material: str
    faltando: int
    obras: int


@dataclass(frozen=True)
class Retrato:
    """``linhas`` é tupla e ``obras`` é frozenset para o retrato ser comparável
    com ``==``: é assim que os gatilhos detectam que nada mudou. O frozenset
    ainda garante que a comparação não dependa da ordem em que as obras saíram
    do banco. Quem ordena para exibição é o formatador."""

    linhas: tuple
    obras: frozenset


def consolidar(instalacoes):
    """Retrato do que falta, somando todas as obras."""
    totais = {}
    obras = set()

    for instalacao in instalacoes:
        contribuiu = False
        for material in instalacao.materiais:
            faltando = max(0, material.faltando)
            if faltando == 0:
                continue
            acumulado = totais.setdefault(material.nome, [0, 0])
            acumulado[0] += faltando
            acumulado[1] += 1
            contribuiu = True
        if contribuiu:
            obras.add(instalacao.nome)

    linhas = tuple(
        LinhaConsolidada(material=nome, faltando=faltando, obras=quantas)
        for nome, (faltando, quantas) in sorted(
            totais.items(), key=lambda item: (-item[1][0], item[0])
        )
    )
    return Retrato(linhas=linhas, obras=frozenset(obras))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_consolidado.py -v`
Expected: PASS, 6 testes

- [ ] **Step 5: Commit**

```bash
git add consolidado.py tests/test_consolidado.py
git commit -m "Soma por material o que falta em todas as obras"
```

---

### Task 2: A mensagem — `formatar_consolidado()`

**Files:**
- Modify: `consolidado.py`
- Test: `tests/test_consolidado.py`

**Interfaces:**
- Consumes: `Retrato` e `LinhaConsolidada` da Task 1; `ed_parser.MARCA_CONSTRUCAO`.
- Produces: `CABECALHO: str`, `LIMITE_MENSAGEM = 2000`, `LIMITE_LINHA_OBRAS = 300`, `nome_curto(nome) -> str`, `formatar_consolidado(retrato, quando) -> str`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_consolidado.py`:

```python
import datetime

QUANDO = datetime.datetime(2026, 9, 5, 14, 32, tzinfo=datetime.timezone.utc)


def test_corta_o_prefixo_de_construcao_do_nome():
    assert consolidado.nome_curto(
        "Planetary Construction Site: Pedder's Forge"
    ) == "Pedder's Forge"


def test_nome_sem_prefixo_aparece_inteiro():
    assert consolidado.nome_curto("Victoria Wolf Steel") == "Victoria Wolf Steel"


def test_nome_que_ficaria_vazio_apos_o_corte_aparece_inteiro():
    assert consolidado.nome_curto("Construction Site:") == "Construction Site:"


def test_mensagem_lista_as_obras_em_ordem_alfabetica_e_sem_prefixo():
    retrato = consolidado.consolidar([
        _obra("Orbital Construction Site: Victoria Wolf Steel", [_material("Steel", 10, 0)]),
        _obra("Planetary Construction Site: Pedder's Forge", [_material("Steel", 10, 0)]),
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert "Pedder's Forge · Victoria Wolf Steel" in texto
    assert "Construction Site:" not in texto


def test_a_ordem_das_obras_nao_depende_da_iteracao_do_frozenset():
    retrato = consolidado.consolidar([
        _obra(f"Obra {letra}", [_material("Steel", 10, 0)]) for letra in "ZMAK"
    ])

    primeira = consolidado.formatar_consolidado(retrato, QUANDO)
    outra_ordem = consolidado.Retrato(
        linhas=retrato.linhas, obras=frozenset(reversed(sorted(retrato.obras)))
    )

    assert consolidado.formatar_consolidado(outra_ordem, QUANDO) == primeira


def test_muitas_obras_cortam_a_linha_de_nomes_e_somam_o_resto():
    retrato = consolidado.consolidar([
        _obra(f"Obra Com Nome Bem Comprido Numero {i:02d}", [_material("Steel", 10, 0)])
        for i in range(40)
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)
    linha_obras = texto.splitlines()[1]
    mostradas = linha_obras.split(" · +")[0].split(" · ")

    assert len(linha_obras) <= consolidado.LIMITE_LINHA_OBRAS + 20
    assert f"+{40 - len(mostradas)} outras" in linha_obras


def test_cabe_em_2000_caracteres_com_muitos_materiais():
    retrato = consolidado.consolidar([
        _obra("A", [_material(f"Material Numero {i:03d}", 1000 - i, 0) for i in range(300)])
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert len(texto) <= consolidado.LIMITE_MENSAGEM


def test_o_resumo_do_corte_bate_com_o_que_ficou_de_fora():
    retrato = consolidado.consolidar([
        _obra("A", [_material(f"Material Numero {i:03d}", 1000 - i, 0) for i in range(300)])
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)
    mostrados = sum(1 for l in texto.splitlines() if l.startswith("Material Numero"))
    cortados = 300 - mostrados
    soma_cortada = sum(l.faltando for l in retrato.linhas[mostrados:])

    assert f"+{cortados} materiais menores ({soma_cortada} no total)" in texto


def test_sem_corte_nao_ha_linha_de_resumo():
    retrato = consolidado.consolidar([_obra("A", [_material("Steel", 100, 0)])])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert "materiais menores" not in texto


def test_o_cabecalho_nao_e_confundido_com_mensagem_de_obra():
    """Se casasse, a reconciliação trataria o consolidado como uma obra."""
    retrato = consolidado.consolidar([_obra("A", [_material("Steel", 100, 0)])])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert ed_parser.nome_na_mensagem(texto) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_consolidado.py -v`
Expected: FAIL com `AttributeError: module 'consolidado' has no attribute 'nome_curto'`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `consolidado.py` — o `import ed_parser` vai junto do `from dataclasses import dataclass` no topo:

```python
CABECALHO = "🧾 **Consolidado do esquadrão**"
LIMITE_MENSAGEM = 2000
LIMITE_LINHA_OBRAS = 300

LARGURA_MATERIAL = 25
LARGURA_FALTAM = 7
LARGURA_OBRAS = 5


def nome_curto(nome):
    """Nome da obra sem o prefixo de construção, que é igual em todas."""
    posicao = nome.find(ed_parser.MARCA_CONSTRUCAO)
    if posicao == -1:
        return nome
    curto = nome[posicao + len(ed_parser.MARCA_CONSTRUCAO):].strip()
    return curto or nome


def _linha_de_obras(nomes):
    """Nomes separados por '·', cortados no teto, com '+N outras' no fim."""
    curtos = sorted(nome_curto(n) for n in nomes)
    escolhidos = []
    tamanho = 0
    for curto in curtos:
        adicional = len(curto) + (3 if escolhidos else 0)
        if tamanho + adicional > LIMITE_LINHA_OBRAS:
            break
        escolhidos.append(curto)
        tamanho += adicional

    linha = " · ".join(escolhidos)
    restantes = len(curtos) - len(escolhidos)
    if not restantes:
        return linha
    return f"{linha} · +{restantes} outras" if linha else f"+{restantes} outras"


def _resumo_do_corte(linhas):
    if not linhas:
        return ""
    total = sum(l.faltando for l in linhas)
    return f"+{len(linhas)} materiais menores ({total} no total)"


def formatar_consolidado(retrato, quando):
    """Mensagem do Discord, cortada para caber em LIMITE_MENSAGEM.

    A prioridade do orçamento é: cabeçalho e rodapé nunca saem, depois a linha
    de nomes das obras, depois os materiais na ordem decrescente, e por último
    a linha de resumo do que foi cortado.
    """
    quantas = len(retrato.obras)
    topo = (
        f"{'Material':<{LARGURA_MATERIAL}} | {'Faltam':>{LARGURA_FALTAM}} | "
        f"{'Obras':>{LARGURA_OBRAS}}"
    )

    fixo = [f"{CABECALHO} `{quantas} obra{'s' if quantas != 1 else ''}`"]
    linha_obras = _linha_de_obras(retrato.obras)
    if linha_obras:
        fixo.append(linha_obras)
    fixo += ["", "```", topo, "-" * len(topo)]
    fim = ["```", f"-# atualizado às {quando.strftime('%H:%M')} UTC"]

    def tamanho(corpo, resumo):
        partes = fixo + corpo + ([resumo] if resumo else []) + fim
        return len("\n".join(partes))

    corpo = []
    for indice, linha in enumerate(retrato.linhas):
        candidata = (
            f"{linha.material:<{LARGURA_MATERIAL}} | {linha.faltando:>{LARGURA_FALTAM}} | "
            f"{linha.obras:>{LARGURA_OBRAS}}"
        )
        if tamanho(corpo + [candidata], _resumo_do_corte(retrato.linhas[indice + 1:])) > LIMITE_MENSAGEM:
            break
        corpo.append(candidata)

    resumo = _resumo_do_corte(retrato.linhas[len(corpo):])
    return "\n".join(fixo + corpo + ([resumo] if resumo else []) + fim)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_consolidado.py -v`
Expected: PASS, 16 testes

- [ ] **Step 5: Commit**

```bash
git add consolidado.py tests/test_consolidado.py
git commit -m "Formata o consolidado dentro do limite do Discord"
```

---

### Task 3: Os gatilhos — `decidir_acao()`

**Files:**
- Modify: `consolidado.py`
- Test: `tests/test_consolidado.py`

**Interfaces:**
- Consumes: `Retrato` da Task 1.
- Produces: `JANELA_REPOST_HORAS = 12`, `COOLDOWN_REPOST_MINUTOS = 30`, `decidir_acao(antes, depois, ultimo_repost, agora) -> str` devolvendo `"repostar"`, `"editar"` ou `"nada"`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_consolidado.py`:

```python
AGORA = datetime.datetime(2026, 9, 5, 20, 0, tzinfo=datetime.timezone.utc)
HA_UMA_HORA = AGORA - datetime.timedelta(hours=1)
HA_DEZ_MINUTOS = AGORA - datetime.timedelta(minutes=10)
HA_UM_DIA = AGORA - datetime.timedelta(days=1)


def _retrato(*obras):
    return consolidado.consolidar(list(obras))


def test_nada_mudou_nao_faz_nada():
    r = _retrato(_obra("A", [_material("Steel", 100, 0)]))

    assert consolidado.decidir_acao(r, r, HA_UMA_HORA, AGORA) == "nada"


def test_obra_nova_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "repostar"


def test_obra_que_ficou_pronta_reposta():
    antes = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 100)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "repostar"


def test_material_que_zerou_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "repostar"


def test_passou_a_janela_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_UM_DIA, AGORA) == "repostar"


def test_progresso_comum_so_edita():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "editar"


def test_sem_repost_anterior_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, None, AGORA) == "repostar"


def test_cooldown_vence_a_obra_nova():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"


def test_cooldown_vence_a_obra_pronta():
    antes = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 100)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"


def test_cooldown_vence_o_material_zerado():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"


def test_cooldown_vence_a_janela():
    """Impossível na prática, mas fixa a precedência: o cooldown vem primeiro."""
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_consolidado.py -v`
Expected: FAIL com `AttributeError: module 'consolidado' has no attribute 'decidir_acao'`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `consolidado.py` — o `import datetime` vai para o topo do arquivo:

```python
JANELA_REPOST_HORAS = 12
COOLDOWN_REPOST_MINUTOS = 30


def decidir_acao(antes, depois, ultimo_repost, agora):
    """"repostar", "editar" ou "nada".

    O cooldown tem precedência sobre todos os gatilhos: sem ele, "material
    zerou" faria a mensagem pular para o fim do canal várias vezes num dia de
    muita entrega.
    """
    if antes == depois:
        return "nada"

    if ultimo_repost is not None:
        desde = agora - ultimo_repost
        if desde < datetime.timedelta(minutes=COOLDOWN_REPOST_MINUTOS):
            return "editar"
        if desde > datetime.timedelta(hours=JANELA_REPOST_HORAS):
            return "repostar"
    else:
        return "repostar"

    if antes.obras != depois.obras:
        return "repostar"

    materiais_antes = {l.material for l in antes.linhas}
    materiais_depois = {l.material for l in depois.linhas}
    if materiais_antes - materiais_depois:
        return "repostar"

    return "editar"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_consolidado.py -v`
Expected: PASS, 27 testes

- [ ] **Step 5: Commit**

```bash
git add consolidado.py tests/test_consolidado.py
git commit -m "Decide entre repostar, editar e não fazer nada"
```

---

### Task 4: A tabela `meta`

**Files:**
- Modify: `armazenamento.py`
- Test: `tests/test_armazenamento.py`

**Interfaces:**
- Produces: `Armazenamento.obter_meta(chave, padrao=None) -> str | None` e `Armazenamento.definir_meta(chave, valor) -> None`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_armazenamento.py`:

```python
def test_meta_devolve_o_padrao_quando_a_chave_nao_existe(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))

    assert banco.obter_meta("consolidado_message_id") is None
    assert banco.obter_meta("consolidado_message_id", "vazio") == "vazio"


def test_meta_guarda_e_devolve(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))

    banco.definir_meta("consolidado_message_id", "12345")

    assert banco.obter_meta("consolidado_message_id") == "12345"


def test_meta_sobrescreve_a_chave_existente(tmp_path):
    banco = armazenamento.Armazenamento(str(tmp_path / "estado.db"))

    banco.definir_meta("consolidado_message_id", "12345")
    banco.definir_meta("consolidado_message_id", "67890")

    assert banco.obter_meta("consolidado_message_id") == "67890"


def test_meta_sobrevive_a_reabertura_do_banco(tmp_path):
    caminho = str(tmp_path / "estado.db")
    armazenamento.Armazenamento(caminho).definir_meta("chave", "valor")

    assert armazenamento.Armazenamento(caminho).obter_meta("chave") == "valor"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_armazenamento.py -v -k meta`
Expected: FAIL com `AttributeError: 'Armazenamento' object has no attribute 'obter_meta'`

- [ ] **Step 3: Implementar o mínimo**

Em `armazenamento.py`, acrescentar a constante logo abaixo de `ESQUEMA`:

```python
ESQUEMA_META = """
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
)
"""
```

Em `__init__`, executar o esquema novo logo depois do atual — a linha
`self._conexao.execute(ESQUEMA)` passa a ser seguida de:

```python
        self._conexao.execute(ESQUEMA_META)
```

E acrescentar os dois métodos logo depois de `marcar_finalizado`:

```python
    def obter_meta(self, chave, padrao=None):
        linha = self._conexao.execute(
            "SELECT valor FROM meta WHERE chave = ?", (chave,)
        ).fetchone()
        return linha["valor"] if linha else padrao

    def definir_meta(self, chave, valor):
        self._conexao.execute(
            "INSERT INTO meta (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, str(valor)),
        )
        self._conexao.commit()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/test_armazenamento.py -v`
Expected: PASS, incluindo os 4 novos

- [ ] **Step 5: Commit**

```bash
git add armazenamento.py tests/test_armazenamento.py
git commit -m "Guarda pares chave-valor numa tabela meta"
```

---

### Task 5: `finalizado` passa a significar "pronta"

**Files:**
- Modify: `servidor.py` (função `verificar_finalizacoes`)
- Test: `tests/test_servidor.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `esta_pronta(instalacao) -> bool` e `finalizar_se_pronta(banco_alvo, registro) -> bool`.

**Nota sobre os testes deste arquivo:** `servidor` em `tests/test_servidor.py` é
uma **fixture** (linha 13), não um import de módulo. Todo teste que toca o
servidor recebe `servidor` como parâmetro e usa `servidor.banco` — a fixture
aponta `CAMINHO_DB` para um `tmp_path` próprio, então cada teste tem banco
isolado. Não criar `armazenamento.Armazenamento(...)` à mão.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_servidor.py`:

```python
# --- finalizado significa "pronta", não "parada" -----------------------------


def _obra_de_teste(nome, requerido, fornecido, market_id):
    import ed_parser

    return ed_parser.instalacao_de_payload(
        nome,
        [{"Name_Localised": "Steel", "RequiredAmount": requerido, "ProvidedAmount": fornecido}],
        market_id=market_id,
    )


def test_obra_parada_com_material_faltando_continua_pendente(servidor):
    """Antes, 'finalizado' virava 1 só por inatividade — o que esvaziaria o
    consolidado justamente das obras que mais precisam de material."""
    servidor.banco.salvar(_obra_de_teste("Obra Parada", 100, 10, 1), message_id=1)

    finalizou = servidor.finalizar_se_pronta(servidor.banco, servidor.banco.obter("Obra Parada"))

    assert finalizou is False
    assert servidor.banco.obter("Obra Parada").finalizado is False


def test_obra_completa_e_finalizada(servidor):
    servidor.banco.salvar(_obra_de_teste("Obra Pronta", 100, 100, 2), message_id=2)

    finalizou = servidor.finalizar_se_pronta(servidor.banco, servidor.banco.obter("Obra Pronta"))

    assert finalizou is True
    assert servidor.banco.obter("Obra Pronta").finalizado is True


def test_obra_sem_materiais_nao_e_finalizada(servidor):
    """all([]) é True: sem guarda, uma obra sem materiais viraria 'pronta'."""
    import ed_parser

    vazia = ed_parser.instalacao_de_payload("Obra Vazia", [], market_id=3)
    servidor.banco.salvar(vazia, message_id=3)

    finalizou = servidor.finalizar_se_pronta(servidor.banco, servidor.banco.obter("Obra Vazia"))

    assert finalizou is False
    assert servidor.banco.obter("Obra Vazia").finalizado is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_servidor.py -v -k finaliz`
Expected: FAIL com `AttributeError: module 'servidor' has no attribute 'finalizar_se_pronta'`

- [ ] **Step 3: Implementar o mínimo**

Em `servidor.py`, acrescentar as duas funções logo acima de `verificar_finalizacoes`:

```python
def esta_pronta(instalacao):
    """Obra sem material nenhum não conta como pronta: all([]) é True."""
    return bool(instalacao.materiais) and all(m.completo for m in instalacao.materiais)


def finalizar_se_pronta(banco_alvo, registro):
    """Marca finalizado só quando os materiais estão completos.

    Antes isto era incondicional depois de TEMPO_FINALIZACAO_HORAS, e
    'finalizado' acabava significando 'ninguém reportou nas últimas 2 horas'.
    O consolidado depende de 'finalizado' querer dizer 'pronta'.
    """
    if not esta_pronta(registro.instalacao):
        return False
    banco_alvo.marcar_finalizado(registro.instalacao.nome)
    return True
```

E o corpo do `for` em `verificar_finalizacoes` passa a ser:

```python
        for registro in banco.listar(pendentes=True):
            horas = (agora - registro.ultima_atualizacao).total_seconds() / 3600
            if horas < TEMPO_FINALIZACAO_HORAS:
                continue
            if not esta_pronta(registro.instalacao):
                continue
            try:
                mensagem = await buscar_mensagem(canal, registro.message_id)
                if mensagem is not None:
                    await adicionar_reacao_check(mensagem, registro.instalacao.materiais)
                finalizar_se_pronta(banco, registro)
                print(f"{CHECK} Finalizado automaticamente: {registro.instalacao.nome}")
            except Exception as e:
                print(f"Erro ao finalizar {registro.instalacao.nome}: {e}")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add servidor.py tests/test_servidor.py
git commit -m "Finaliza a obra só quando os materiais estão completos"
```

---

### Task 6: Reconciliar a mensagem de consolidado

**Files:**
- Modify: `servidor.py`
- Test: `tests/test_servidor.py`

**Interfaces:**
- Consumes: `consolidado.CABECALHO` (Task 2); `obter_meta`/`definir_meta` (Task 4).
- Produces: `e_mensagem_de_consolidado(conteudo) -> bool`, `escolher_consolidado(mensagens) -> tuple`, `reconciliar_consolidado(canal, autor)` (corrotina).

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_servidor.py`. O `MensagemDatada` estende o
`MensagemComConteudo` que já existe no arquivo (linha 203), acrescentando o que
a reconciliação do consolidado precisa:

```python
# --- reconciliação da mensagem de consolidado --------------------------------


class MensagemDatada(MensagemComConteudo):
    def __init__(self, id, content, author, created_at):
        super().__init__(id, content, author)
        self.created_at = created_at
        self.apagada = False
        self.editada_para = None

    async def delete(self):
        self.apagada = True

    async def edit(self, content=None):
        self.editada_para = content


def _quando(horas):
    import datetime

    return datetime.datetime(2026, 9, 5, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=horas)


def test_reconhece_a_mensagem_de_consolidado(servidor):
    import consolidado

    assert servidor.e_mensagem_de_consolidado(consolidado.CABECALHO + " `3 obras`")


def test_mensagem_de_obra_nao_e_confundida_com_consolidado(servidor):
    assert not servidor.e_mensagem_de_consolidado(
        "📍 **Materiais para instalação:** `Pedder's Forge`"
    )


def test_escolhe_a_mais_recente_e_separa_as_outras(servidor):
    import consolidado

    bot = UsuarioFalso(42)
    mensagens = [
        MensagemDatada(1, consolidado.CABECALHO, bot, _quando(0)),
        MensagemDatada(2, consolidado.CABECALHO, bot, _quando(2)),
        MensagemDatada(3, consolidado.CABECALHO, bot, _quando(1)),
    ]

    escolhida, apagar = servidor.escolher_consolidado(mensagens)

    assert escolhida.id == 2
    assert sorted(m.id for m in apagar) == [1, 3]


def test_sem_consolidado_no_canal_nao_escolhe_nada(servidor):
    escolhida, apagar = servidor.escolher_consolidado([])

    assert escolhida is None
    assert apagar == []


def test_reconciliacao_adota_o_id_e_o_horario_da_mensagem(servidor):
    import consolidado

    bot = UsuarioFalso(42)
    canal = CanalFalso([MensagemDatada(777, consolidado.CABECALHO, bot, _quando(5))], bot=bot)

    asyncio.run(servidor.reconciliar_consolidado(canal, autor=UsuarioFalso(42)))

    assert servidor.banco.obter_meta("consolidado_message_id") == "777"
    assert servidor.banco.obter_meta("consolidado_ultimo_repost") == _quando(5).isoformat()


def test_reconciliacao_apaga_os_consolidados_duplicados(servidor):
    """Sem isso, cada restart do Render deixa um consolidado órfão no canal."""
    import consolidado

    bot = UsuarioFalso(42)
    velha = MensagemDatada(1, consolidado.CABECALHO, bot, _quando(0))
    nova = MensagemDatada(2, consolidado.CABECALHO, bot, _quando(3))
    canal = CanalFalso([nova, velha], bot=bot)

    asyncio.run(servidor.reconciliar_consolidado(canal, autor=UsuarioFalso(42)))

    assert velha.apagada is True
    assert nova.apagada is False
    assert servidor.banco.obter_meta("consolidado_message_id") == "2"


def test_reconciliacao_de_obras_ignora_a_mensagem_de_consolidado(servidor):
    """O cabeçalho não casa com _NOME_NA_MENSAGEM, então nenhuma obra fantasma
    entra no banco a partir do consolidado."""
    import consolidado

    bot = UsuarioFalso(42)
    canal = CanalFalso([MensagemDatada(9, consolidado.CABECALHO, bot, _quando(0))], bot=bot)

    asyncio.run(servidor.reconciliar_com_o_canal(canal, autor=UsuarioFalso(42)))

    assert servidor.banco.listar() == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_servidor.py -v -k consolidado`
Expected: FAIL com `AttributeError: module 'servidor' has no attribute 'e_mensagem_de_consolidado'`

- [ ] **Step 3: Implementar o mínimo**

Em `servidor.py`, acrescentar `import consolidado` junto de `import armazenamento`
e `import ed_parser`, e estas funções logo depois de `reconciliar_com_o_canal`:

```python
def e_mensagem_de_consolidado(conteudo):
    return (conteudo or "").startswith(consolidado.CABECALHO)


def escolher_consolidado(mensagens):
    """A mais recente é adotada; as outras são lixo de restarts anteriores.

    O disco do Render é efêmero, então o banco (e o id guardado) somem a cada
    restart. Sem esta varredura, cada restart posta um consolidado novo e os
    antigos ficam para sempre no canal.
    """
    if not mensagens:
        return None, []
    ordenadas = sorted(mensagens, key=lambda m: m.created_at, reverse=True)
    return ordenadas[0], ordenadas[1:]


async def reconciliar_consolidado(canal, autor):
    """Reencontra a mensagem de consolidado depois de um restart."""
    encontradas = []
    async for mensagem in canal.history(limit=MENSAGENS_A_VARRER):
        if mensagem.author.id != autor.id:
            continue
        if e_mensagem_de_consolidado(mensagem.content):
            encontradas.append(mensagem)

    escolhida, a_apagar = escolher_consolidado(encontradas)
    for antiga in a_apagar:
        try:
            await antiga.delete()
        except Exception as e:
            print(f"Erro ao apagar consolidado duplicado: {e}")

    if escolhida is None:
        return None

    banco.definir_meta("consolidado_message_id", escolhida.id)
    # O created_at da adotada é o último repost. Sem isso, todo restart
    # contaria como "faz mais de 12h" e dispararia um repost à toa.
    banco.definir_meta("consolidado_ultimo_repost", escolhida.created_at.isoformat())
    return escolhida
```

E, em `on_ready`, logo depois da chamada a `reconciliar_com_o_canal`:

```python
            await reconciliar_consolidado(canal, autor=client.user)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add servidor.py tests/test_servidor.py
git commit -m "Reencontra o consolidado no canal e apaga os duplicados"
```

---

### Task 7: Ligar o consolidado ao relato aceito

**Files:**
- Modify: `servidor.py` (`receber_dados`)
- Test: `tests/test_servidor.py`

**Interfaces:**
- Consumes: tudo das tarefas 1 a 6. Nos testes, reaproveita dois auxiliares já
  definidos em tarefas anteriores no mesmo arquivo: `_obra_de_teste` (Task 5) e
  `_quando` (Task 6), além de `CanalFalso`, `UsuarioFalso` e `MensagemDatada`.
- Produces: `retrato_atual(banco_alvo) -> consolidado.Retrato` e `atualizar_consolidado(canal, antes, depois, agora)` (corrotina).

`retrato_atual` recebe o banco por parâmetro porque é chamada nos testes com
bancos diferentes; `atualizar_consolidado` usa o `banco` de módulo, como as
outras corrotinas do arquivo. A assimetria é deliberada — não "uniformizar".

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_servidor.py`:

```python
# --- o consolidado a cada relato aceito --------------------------------------


class CanalQueRegistra(CanalFalso):
    """CanalFalso + send(), para ver o que o servidor postou."""

    def __init__(self, mensagens=(), bot=None):
        super().__init__(mensagens, bot=bot)
        self.enviadas = []
        self._proximo_id = 1000

    async def send(self, conteudo):
        self._proximo_id += 1
        nova = MensagemDatada(self._proximo_id, conteudo, self.bot, _quando(9))
        self.enviadas.append(nova)
        self._mensagens.append(nova)
        return nova


def test_retrato_atual_ignora_as_obras_finalizadas(servidor):
    servidor.banco.salvar(_obra_de_teste("Aberta", 100, 0, 1), message_id=1)
    servidor.banco.salvar(_obra_de_teste("Pronta", 100, 100, 2), message_id=2)
    servidor.banco.marcar_finalizado("Pronta")

    retrato = servidor.retrato_atual(servidor.banco)

    assert retrato.obras == frozenset({"Aberta"})
    assert [l.material for l in retrato.linhas] == ["Steel"]


def test_sem_mensagem_anterior_o_consolidado_e_postado(servidor):
    import consolidado

    canal = CanalQueRegistra(bot=UsuarioFalso(42))
    antes = consolidado.consolidar([])
    servidor.banco.salvar(_obra_de_teste("Aberta", 100, 0, 1), message_id=1)
    depois = servidor.retrato_atual(servidor.banco)

    asyncio.run(servidor.atualizar_consolidado(canal, antes, depois, _quando(9)))

    assert len(canal.enviadas) == 1
    assert consolidado.CABECALHO in canal.enviadas[0].content
    assert servidor.banco.obter_meta("consolidado_message_id") == str(canal.enviadas[0].id)


def test_progresso_comum_edita_a_mensagem_existente(servidor):
    import consolidado

    bot = UsuarioFalso(42)
    existente = MensagemDatada(500, consolidado.CABECALHO, bot, _quando(8))
    canal = CanalQueRegistra([existente], bot=bot)
    servidor.banco.definir_meta("consolidado_message_id", 500)
    servidor.banco.definir_meta("consolidado_ultimo_repost", _quando(8).isoformat())

    servidor.banco.salvar(_obra_de_teste("Aberta", 100, 0, 1), message_id=1)
    antes = servidor.retrato_atual(servidor.banco)
    servidor.banco.salvar(_obra_de_teste("Aberta", 100, 30, 1), message_id=1)
    depois = servidor.retrato_atual(servidor.banco)

    # uma hora depois: passou o cooldown de 30 min, não passou a janela de 12 h
    asyncio.run(servidor.atualizar_consolidado(canal, antes, depois, _quando(9)))

    assert canal.enviadas == []
    assert existente.editada_para is not None
    assert existente.apagada is False


def test_obra_nova_apaga_a_anterior_e_reposta(servidor):
    import consolidado

    bot = UsuarioFalso(42)
    existente = MensagemDatada(500, consolidado.CABECALHO, bot, _quando(8))
    canal = CanalQueRegistra([existente], bot=bot)
    servidor.banco.definir_meta("consolidado_message_id", 500)
    servidor.banco.definir_meta("consolidado_ultimo_repost", _quando(8).isoformat())

    servidor.banco.salvar(_obra_de_teste("Aberta", 100, 0, 1), message_id=1)
    antes = servidor.retrato_atual(servidor.banco)
    servidor.banco.salvar(_obra_de_teste("Nova", 50, 0, 2), message_id=2)
    depois = servidor.retrato_atual(servidor.banco)

    asyncio.run(servidor.atualizar_consolidado(canal, antes, depois, _quando(9)))

    assert existente.apagada is True
    assert len(canal.enviadas) == 1
    assert servidor.banco.obter_meta("consolidado_ultimo_repost") == _quando(9).isoformat()


def test_nada_mudou_nao_toca_no_canal(servidor):
    import consolidado

    bot = UsuarioFalso(42)
    existente = MensagemDatada(500, consolidado.CABECALHO, bot, _quando(8))
    canal = CanalQueRegistra([existente], bot=bot)
    servidor.banco.definir_meta("consolidado_message_id", 500)
    servidor.banco.definir_meta("consolidado_ultimo_repost", _quando(8).isoformat())

    servidor.banco.salvar(_obra_de_teste("Aberta", 100, 0, 1), message_id=1)
    retrato = servidor.retrato_atual(servidor.banco)

    asyncio.run(servidor.atualizar_consolidado(canal, retrato, retrato, _quando(9)))

    assert canal.enviadas == []
    assert existente.editada_para is None
    assert existente.apagada is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest tests/test_servidor.py -v -k "retrato_atual or consolidado_e_postado or edita_a_mensagem or apaga_a_anterior or nao_toca_no_canal"`
Expected: FAIL com `AttributeError: module 'servidor' has no attribute 'retrato_atual'`

- [ ] **Step 3: Implementar o mínimo**

Em `servidor.py`, acrescentar logo depois de `escolher_consolidado`:

```python
def retrato_atual(banco_alvo):
    """Consolidado do que está aberto agora, direto do banco."""
    return consolidado.consolidar(
        [r.instalacao for r in banco_alvo.listar(pendentes=True)]
    )


async def atualizar_consolidado(canal, antes, depois, agora):
    """Reposta, edita ou não faz nada, conforme decidir_acao."""
    bruto = banco.obter_meta("consolidado_ultimo_repost")
    ultimo_repost = datetime.datetime.fromisoformat(bruto) if bruto else None

    acao = consolidado.decidir_acao(antes, depois, ultimo_repost, agora)
    if acao == "nada":
        return

    texto = consolidado.formatar_consolidado(depois, agora)
    guardado = banco.obter_meta("consolidado_message_id")
    mensagem = await buscar_mensagem(canal, int(guardado)) if guardado else None

    if acao == "editar" and mensagem is not None:
        await mensagem.edit(content=texto)
        return

    if mensagem is not None:
        try:
            await mensagem.delete()
        except Exception as e:
            print(f"Erro ao apagar o consolidado anterior: {e}")

    nova = await canal.send(texto)
    banco.definir_meta("consolidado_message_id", nova.id)
    banco.definir_meta("consolidado_ultimo_repost", agora.isoformat())
```

Em `receber_dados`, capturar o retrato **antes** do `banco.salvar`. Logo depois
do bloco

```python
    if not deve_publicar(instalacao):
        return JSONResponse(content={"status": "ignorado"})
```

acrescentar:

```python
    antes = retrato_atual(banco)
```

E, ao fim da função, depois de
`await adicionar_reacao_check(nova_msg, instalacao.materiais)` e antes do
`return`:

```python
    try:
        await atualizar_consolidado(canal, antes, retrato_atual(banco), agora)
    except Exception as e:
        # O relato da obra já foi publicado; o consolidado é acessório e não
        # pode derrubar a resposta ao cliente.
        print(f"Erro ao atualizar o consolidado: {e}")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 5: Commit**

```bash
git add servidor.py tests/test_servidor.py
git commit -m "Atualiza o consolidado a cada relato aceito"
```

---

## Depois do plano

A linha de base era 122 testes; o plano fecha em torno de 160.

Duas coisas os testes não conseguem provar contra o Discord real, e precisam de
olho no primeiro deploy:

1. **A mensagem de consolidado aparece uma vez só depois de um restart.** É o
   caso que a Task 6 existe para cobrir, e o mais fácil de dar errado em
   produção — o banco é apagado a cada restart do Render.
2. **O `message.edit()` funciona na mensagem do próprio bot** sem limite de
   idade. Se por algum motivo não funcionar, o caminho de repost já é o
   fallback natural e a correção é forçar `acao = "repostar"`.
