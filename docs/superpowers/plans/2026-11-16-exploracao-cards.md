# Cards, modais e tabela de preços da aba Exploração — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar os blocos de texto da aba Exploração por cards clicáveis que abrem modais, e adicionar a tabela de preços da Vista Genomics com busca.

**Architecture:** O backend (`exploracao.py`, `precos_vista.py`) ganha campos novos no resumo — somas das amostras prováveis, multiplicador observado nas vendas e a lista de preços. O frontend continua num único `painel.html` com JS puro: cards `<button>`, um `<dialog>` reaproveitado e uma tabela de preços desenhada uma vez só.

**Tech Stack:** Python 3 (stdlib), pytest, HTML/CSS/JS sem build; os testes de JS rodam o `<script>` do painel no `node` com um DOM falso (`tests/test_painel.py`).

**Spec:** `docs/superpowers/specs/2026-11-16-exploracao-cards-design.md`

## Global Constraints

- Tudo no worktree `.claude/worktrees/aba-exploracao`, branch `worktree-aba-exploracao`. Rodar testes com `.venv/bin/python -m pytest -q` (o `.venv` é symlink e nunca vai para o git).
- Multiplicador: constante `BONUS_PRIMEIRO_REGISTRO = 5` em `exploracao.py`; nunca duplicar o 5 em outro lugar (o JS recebe `com_bonus` pronto e o multiplicador pelo JSON).
- `total_base` e `total_com_bonus` continuam no resumo, com o mesmo significado.
- Sem dependências novas, sem CDN: o painel roda offline.
- Valores em créditos aparecem com `mi(n)` (já existe: `5000000 -> "5,0 mi"`).
- Textos da interface em PT-BR. Card A bordo: rótulo `com bônus (×5, estimado)`; se houver multiplicador observado diferente de 5, `com bônus (×5, observado ×N)` com N em uma casa decimal e vírgula.
- `prefers-reduced-motion: reduce` desliga transições e animações.
- Paleta existente: fundo `#14100c`, cartão `#1e1813`, borda `#3a2f24`, laranja `#ff8c1a`, texto `#e8dcc8`, rótulo `#9a8b76`.

## Review Focus

1. **Modal aberto durante o polling de 5 s** — o conteúdo deve trocar no lugar, sem fechar e sem voltar a rolagem ao topo. → teste em Task 2 (`test_modal_aberto_e_reescrito_no_polling`).
2. **Falha de fetch com o modal aberto** — `falhaExploracao()` não pode apagar o modal nem os cards já desenhados de forma que o modal fique órfão; o modal mantém o último conteúdo. → teste em Task 2 (`test_falha_nao_mexe_no_modal`).
3. **Venda com `Value` 0 e `Bonus` > 0** (ou `Value` ausente) — não pode dividir por zero; o item fica fora do multiplicador. → teste em Task 1.
4. **Espécie provável sem preço** — conta em `provaveis_quantidade`, fica fora das duas somas. → teste em Task 1.
5. **Busca com acento/caixa e o polling** — "ACIES", "acíes" acham "Bacterium Acies"; o polling não redesenha a tabela nem limpa o filtro. → testes em Task 3.

---

### Task 1: Backend — somas prováveis, multiplicador observado e lista de preços

**Files:**
- Modify: `precos_vista.py` (classe `Precos`, `carregar_precos`)
- Modify: `exploracao.py` (`_a_bordo`, `resumo`)
- Test: `tests/test_exploracao.py`, `tests/test_precos_vista.py`

**Interfaces:**
- Produces:
  - `Precos(especies, apelidos=None, atualizado_em=None)`; atributo `Precos.atualizado_em: str | None`; método `Precos.lista() -> list[tuple[str, int]]` (nome original como no JSON, preço), ordenada por preço decrescente e, no empate, por nome.
  - `carregar_precos()` passa `dados.get("atualizado_em")`.
  - `resumo()["a_bordo"]` ganha `provaveis_quantidade: int`, `provaveis_base: int`, `provaveis_com_bonus: int`.
  - `resumo()["vendido"]["multiplicador_observado"]: float | None` — média de `(Value + Bonus) / Value` sobre as vendas com `bonus_pago > 0` e valor base > 0, arredondada a 2 casas; `None` se não houver nenhuma.
  - `resumo()["multiplicador"]: int` = `BONUS_PRIMEIRO_REGISTRO`.
  - `resumo()["precos"]: list[{"especie": str, "base": int, "com_bonus": int}]` na ordem de `Precos.lista()`; `resumo()["precos_atualizado_em"]: str | None`.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_precos_vista.py`:

```python
def test_lista_vem_ordenada_por_preco_com_nome_original():
    p = precos_vista.Precos({"Bacterium Acies": 1_000_000, "Aleoida Gravis": 12_934_900,
                             "Bacterium Aurasus": 1_000_000})
    assert p.lista() == [("Aleoida Gravis", 12_934_900), ("Bacterium Acies", 1_000_000),
                         ("Bacterium Aurasus", 1_000_000)]

def test_carregar_precos_traz_a_data_de_atualizacao():
    p = precos_vista.carregar_precos()
    assert p.atualizado_em == "2026-11-14"
    assert len(p.lista()) == 96
```

Em `tests/test_exploracao.py` (usar os helpers `historico_vazio`, `analisa`, `venda_organica`, `ID_ACIES`, `ID_OUTRA` já existentes; a Task 3 desse arquivo define `analisa`):

```python
def test_a_bordo_soma_so_as_provaveis_com_e_sem_multiplicador():
    h = historico_vazio({"Bacterium Acies": 1_000_000, "Outra Especie": 500_000})
    analisa(h, body=1)                                   # provável
    analisa(h, body=2, especie="Outra Especie", especie_id=ID_OUTRA, pisado=True)  # improvável
    ab = h.resumo()["a_bordo"]
    assert (ab["provaveis_quantidade"], ab["provaveis_base"], ab["provaveis_com_bonus"]) == (1, 1_000_000, 5_000_000)
    assert ab["total_base"] == 1_500_000                 # inalterado

def test_provavel_sem_preco_conta_mas_fica_fora_das_somas():
    h = historico_vazio()
    analisa(h, body=1, especie="Especie Nova")
    analisa(h, body=2)
    ab = h.resumo()["a_bordo"]
    assert (ab["provaveis_quantidade"], ab["provaveis_base"], ab["provaveis_com_bonus"]) == (2, 1_000_000, 5_000_000)

def test_multiplicador_observado_ausente_sem_venda_com_bonus():
    h = historico_vazio()
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 0)]), SESSAO)
    assert h.resumo()["vendido"]["multiplicador_observado"] is None

def test_multiplicador_observado_e_a_media_das_vendas_com_bonus():
    h = historico_vazio()
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 4_000_000),
                               (ID_OUTRA, "Outra", 1_000_000, 1_000_000),
                               (ID_OUTRA, "Outra", 0, 3_000_000)]), SESSAO)   # Value 0 ignorado
    assert h.resumo()["vendido"]["multiplicador_observado"] == 3.5

def test_resumo_traz_precos_com_bonus_e_o_multiplicador():
    r = historico_vazio({"Bacterium Acies": 1_000_000, "Aleoida Gravis": 2_000_000}).resumo()
    assert r["multiplicador"] == 5
    assert r["precos"] == [{"especie": "Aleoida Gravis", "base": 2_000_000, "com_bonus": 10_000_000},
                           {"especie": "Bacterium Acies", "base": 1_000_000, "com_bonus": 5_000_000}]
    assert r["precos_atualizado_em"] is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest -q tests/test_exploracao.py tests/test_precos_vista.py`
Expected: os 7 testes novos falham (`AttributeError: lista` / `KeyError: 'provaveis_quantidade'` etc.); os antigos passam.

- [ ] **Step 3: Implementar**

`Precos` guarda também o dicionário original (`self._originais = dict(especies)`) para `lista()`. Em `_vender`, nada muda: o valor base de uma venda é `valor - bonus_pago`. As somas prováveis filtram `a["bonus"] == "provavel"`; as somas pulam `preco_base is None`.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest -q`
Expected: tudo passa (348 + 7).

- [ ] **Step 5: Commit**

```bash
git add precos_vista.py exploracao.py tests/test_exploracao.py tests/test_precos_vista.py
git commit -m "Resumo de exploração traz as prováveis, o multiplicador observado e os preços"
```

---

### Task 2: Frontend — cards, modal e estilo

**Files:**
- Modify: `painel.html` (CSS no `<style>`, markup de `#aba-exploracao`, JS de exploração)
- Test: `tests/test_painel.py` (stub `NODE_STUB_EXPLORACAO` e testes `test_pintar_exploracao_*`)

**Interfaces:**
- Consumes: campos do resumo da Task 1.
- Produces (JS global, usados pela Task 3 e pelos testes):
  - Markup: `#exploracao-cartoes` (div `.cartoes`), `#exploracao-precos` (div, preenchida na Task 3), `<dialog id="modal-exploracao">` com `#modal-titulo`, `#modal-corpo` e botão `#modal-fechar`. O antigo `#exploracao` vira `#exploracao-cartoes`; a mensagem "lendo os journals…" e a de falha vão nele.
  - `let dadosExploracao = null; let modalAberto = null;` (chave do card aberto ou `null`).
  - `function pintarExploracao(d)` — guarda `d` em `dadosExploracao`, desenha os cards; se `modalAberto` não é `null`, chama `preencherModal(modalAberto)`; chama `pintarPrecos(d)` (stub vazio nesta task, implementado na Task 3).
  - `function conteudoModal(chave, d) -> Element` para `chave` em `"a_bordo" | "vendido" | "primeiros"`: devolve o título-resumo e a tabela que hoje estão no bloco correspondente (mesmas colunas, mesmas notas de corte/perda/dados de exploração).
  - `function abrirModal(chave)`, `function fecharModal()`, `function preencherModal(chave)` — `preencherModal` guarda `scrollTop` de `#modal-corpo`, troca os filhos e restaura o `scrollTop`.
- Cards (`<button class="cartao clicavel">` quando têm modal; `<div class="cartao">` quando não):

| chave | rótulo | linhas |
|---|---|---|
| `a_bordo` | A bordo | `${n} amostras · base ${mi(total_base)}` / `prováveis (${q}): ${mi(provaveis_base)} → ${mi(provaveis_com_bonus)}` / rótulo do multiplicador (Global Constraints) |
| `vendido` | Vendido | `${quantidade} amostras · ${mi(total)}` / `exploração: ${mi(exploracao_total)}` / se `multiplicador_observado`: `bônus observado ×${N}` |
| — | Carreira (jogo) | só se `carreira`: `${Organic_Data} amostras · ${mi(Organic_Data_Profits)}` / `${First_Logged} primeiras descobertas` |
| `primeiros` | Primeiro a… | `sistemas ${a} · corpos ${b}` / `mapeou ${c} · pisou ${d}` |
| — | Médias | `por amostra ${mi}` / `por planeta ${mi}` / `por sessão ${mi}` |

- Estilo (CSS): `.cartao.clicavel` com `cursor:pointer`, `text-align:left`, `font:inherit`, `color:inherit`, `transition: transform .15s, border-color .15s, box-shadow .15s`; `:hover`/`:focus-visible` → `translateY(-2px)`, borda `#ff8c1a`, `box-shadow: 0 4px 16px rgba(255,140,26,.15)`. `dialog` com fundo `#1e1813`, borda `#3a2f24`, `max-width: min(900px, 92vw)`, `max-height: 80vh`, corpo com `overflow:auto`; `dialog[open]` com animação `fade+scale` de 0.96→1 em 150 ms; `dialog::backdrop` `rgba(0,0,0,.6)` + `backdrop-filter: blur(3px)`. `tbody tr:hover` com fundo `#241c15`; `td.num, th.num` com `text-align:right; font-variant-numeric: tabular-nums`. Bloco `@media (prefers-reduced-motion: reduce)` zerando `transition` e `animation`.
- Fechar: Esc (nativo), clique no backdrop (`click` no `dialog` com `event.target === dialog`), botão ×; o evento `close` do dialog zera `modalAberto`.

- [ ] **Step 1: Atualizar o stub e escrever os testes que falham**

No `NODE_STUB_EXPLORACAO`, cada nó ganha `scrollTop: 0`, `showModal() { this.open = true; }`, `close() { this.open = false; }`, `addEventListener() {}`, `setAttribute() {}`. `_rodar_pintar_exploracao(dados, extra="")` passa a imprimir `textos(elements['exploracao-cartoes'])` e aceita JS extra rodado depois do `pintarExploracao`. Novo helper `_rodar_js(programa_extra)` que roda o script + stub + o código dado e devolve o stdout.

Reescrever os quatro testes `test_pintar_exploracao_*` existentes: os textos de cards ficam no `exploracao-cartoes`; as tabelas passam a ser conferidas via `textos(conteudoModal('a_bordo'|'vendido'|'primeiros', dados))`. As mesmas asserções de hoje continuam valendo (`"Bacterium Acies"`, `"provável"`, `"5,0 mi"`, `"Plio Eurl IX-Z b14-0 B 1"`, `"previsão errada"`, `"439,5 mi"`, `"lendo os journals"`, `"mostrando 50 de 73"`, `"mostrando 50 de 61"`). O dicionário-base dos testes ganha os campos da Task 1 (`provaveis_*`, `multiplicador: 5`, `multiplicador_observado: None`, `precos: []`, `precos_atualizado_em: None`). Novos:

```python
def test_card_a_bordo_mostra_provaveis_com_e_sem_multiplicador():
    # a_bordo: total_base 7_000_000, provaveis_quantidade 1, provaveis_base 5_000_000, provaveis_com_bonus 25_000_000
    saida = _rodar_pintar_exploracao(dados)
    assert "prováveis (1): 5,0 mi → 25,0 mi" in saida
    assert "×5, estimado" in saida

def test_card_mostra_multiplicador_observado_quando_diverge():
    # vendido.multiplicador_observado = 2.0
    saida = _rodar_pintar_exploracao(dados)
    assert "observado ×2,0" in saida and "bônus observado ×2,0" in saida

def test_card_carreira_some_sem_statistics():
    # carreira None
    assert "Carreira" not in _rodar_pintar_exploracao(dados)

def test_modal_aberto_e_reescrito_no_polling():
    # abre 'vendido', muda scrollTop do corpo para 120, pinta de novo com outra venda
    saida = _rodar_js("abrirModal('vendido'); elements['modal-corpo'].scrollTop = 120;"
                      f"pintarExploracao({json.dumps(dados2)});"
                      "console.log(elements['modal-exploracao'].open, elements['modal-corpo'].scrollTop,"
                      " textos(elements['modal-corpo']).join('|'));")
    assert saida.startswith("true 120") and "Especie Da Segunda Leitura" in saida

def test_falha_nao_mexe_no_modal():
    saida = _rodar_js("abrirModal('vendido'); falhaExploracao();"
                      "console.log(elements['modal-exploracao'].open, textos(elements['modal-corpo']).join('|'));")
    assert saida.startswith("true") and "Aleoida Arcus" in saida
```

(O `_rodar_js` dos dois últimos chama `pintarExploracao(dados)` antes do código extra.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest -q tests/test_painel.py -k exploracao`
Expected: falham com `ReferenceError: conteudoModal is not defined` / texto ausente.

- [ ] **Step 3: Implementar markup, CSS e JS conforme as Interfaces acima**

`falhaExploracao()` só troca o conteúdo de `#exploracao-cartoes` e não toca em `modalAberto` nem no dialog. `blocoExploracao` deixa de ser usado e é removido.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest -q`
Expected: tudo passa.

- [ ] **Step 5: Conferir no navegador**

Run: subir o painel (`.venv/bin/python cliente.py` ou só o `painel.py`, como o README manda) e abrir a aba Exploração. Conferir: hover dos cards, abrir/fechar o modal por clique, Esc, backdrop e ×, e que o modal fica aberto depois de 5 s. Sem journals reais na máquina, servir um `/exploracao.json` com os dados de teste é suficiente.

- [ ] **Step 6: Commit**

```bash
git add painel.html tests/test_painel.py
git commit -m "Aba Exploração com cards, modal e animações"
```

---

### Task 3: Frontend — tabela de preços com busca

**Files:**
- Modify: `painel.html`
- Test: `tests/test_painel.py`

**Interfaces:**
- Consumes: `resumo()["precos"]`, `["precos_atualizado_em"]`, `["multiplicador"]` (Task 1); `#exploracao-precos` e a chamada `pintarPrecos(d)` (Task 2).
- Produces:
  - `function pintarPrecos(d)` — se `d.precos` estiver vazio/ausente, não faz nada; se a tabela já foi desenhada (`precosDesenhados === true`), não faz nada. Senão desenha em `#exploracao-precos`: título `Preços Vista Genomics`, `<input id="busca-precos" placeholder="buscar espécie…">` com `oninput = filtrarPrecos`, tabela com colunas `Espécie`, `Base`, `Com bônus (×${d.multiplicador})` (números em `td.num`), e rodapé `atualizado em ${precos_atualizado_em} · fonte: ed-dsn.net / Canonn`.
  - `function semAcento(s) -> string` — `s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()`.
  - `function filtrarPrecos()` — lê `#busca-precos`.value; cada linha cuja espécie (sem acento) não contém o termo recebe `style.display = "none"`, as outras `""`.

- [ ] **Step 1: Escrever os testes que falham**

```python
PRECOS = [{"especie": "Aleoida Gravis", "base": 12_934_900, "com_bonus": 64_674_500},
          {"especie": "Bacterium Acies", "base": 1_000_000, "com_bonus": 5_000_000}]

def test_tabela_de_precos_mostra_base_e_bonus():
    saida = _rodar_js("console.log(textos(elements['exploracao-precos']).join('|'));")  # dados com PRECOS
    assert "Aleoida Gravis" in saida and "12,9 mi" in saida and "64,7 mi" in saida
    assert "Com bônus (×5)" in saida and "2026-11-14" in saida

def test_busca_ignora_acento_e_caixa():
    saida = _rodar_js("elements['busca-precos'].value = 'ACÍES'; filtrarPrecos();"
                      "console.log(JSON.stringify(linhasVisiveis()));")
    assert json.loads(saida) == ["Bacterium Acies"]

def test_polling_nao_redesenha_a_tabela_nem_limpa_a_busca():
    saida = _rodar_js("elements['busca-precos'].value = 'acies'; filtrarPrecos();"
                      f"pintarExploracao({json.dumps(dados)});"
                      "console.log(elements['busca-precos'].value, JSON.stringify(linhasVisiveis()));")
    assert saida.startswith("acies") and "Aleoida" not in saida

def test_sem_precos_nao_desenha_tabela():
    # dados com precos: []
    assert _rodar_js("console.log(textos(elements['exploracao-precos']).length);").strip() == "0"
```

`linhasVisiveis()` é um helper de teste (no stub) que percorre a árvore de `exploracao-precos`, pega os `tr` com `style.display !== "none"` que têm `td` e devolve o texto da primeira célula. Para o stub achar o input, `pintarPrecos` cria o input com `elemento("input")` e o registra com `id = "busca-precos"`; o stub de `createElement` deve registrar em `elements` quem recebe `id` (usar um setter `set id(v) { elements[v] = this; }`).

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/python -m pytest -q tests/test_painel.py -k "precos or busca"`
Expected: falham (`filtrarPrecos is not defined` / texto ausente).

- [ ] **Step 3: Implementar `pintarPrecos`, `semAcento`, `filtrarPrecos` e o CSS do input** (mesma cara do `.aba`: fundo `#1e1813`, borda `#3a2f24`, foco com borda laranja e `transition` de 150 ms).

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/python -m pytest -q`
Expected: tudo passa.

- [ ] **Step 5: Conferir no navegador** — a busca filtra enquanto digita, e esperar 5 s não limpa o filtro.

- [ ] **Step 6: Commit**

```bash
git add painel.html tests/test_painel.py
git commit -m "Tabela de preços da Vista Genomics com busca na aba Exploração"
```

---

### Task 4: Zip do esquadrão

**Files:**
- Regenerar: `/home/arthur/Documentos/Estudos/botEliteDangerous/../cliente-ed-esquadrao.zip` (= `/home/arthur/Documentos/Estudos/cliente-ed-esquadrao.zip`)

- [ ] **Step 1:** Conferir o conteúdo atual: `unzip -l /home/arthur/Documentos/Estudos/cliente-ed-esquadrao.zip` (17 arquivos em `cliente-ed/`, incluindo o LEIA-ME com a seção "ABA EXPLORAÇÃO").
- [ ] **Step 2:** Substituir no zip só os arquivos mudados (`painel.html`, `exploracao.py`, `precos_vista.py`) pela versão do worktree, sob `cliente-ed/`, preservando os demais e o LEIA-ME. Acrescentar à seção "ABA EXPLORAÇÃO" do LEIA-ME uma linha: "Clique nos cards para ver o detalhe; a tabela de preços fica embaixo, com busca."
- [ ] **Step 3:** `unzip -l` de novo: 17 arquivos, datas novas nos três mudados.
