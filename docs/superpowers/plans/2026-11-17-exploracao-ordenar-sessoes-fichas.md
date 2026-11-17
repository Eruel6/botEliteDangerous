# Ordenar tabelas, gráfico de sessões e ficha do gênero — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na aba Exploração: ordenar qualquer tabela clicando no cabeçalho, mostrar um gráfico de ganhos por sessão e abrir uma ficha do gênero (texto, distância mínima e foto da wiki) ao clicar numa espécie.

**Architecture:** Dados novos no backend: um `generos_exobio.json` lido por `generos_exobio.py`, um campo `genero` nas espécies e as somas por sessão em `Historico.resumo()`. No `painel.html` (JS puro, sem build) entram a ordenação genérica em `tabelaTexto`, um card "Sessões" com gráfico SVG e a ficha no mesmo `<dialog>`, com a foto buscada na hora pela API da wiki Fandom.

**Tech Stack:** Python 3 stdlib + pytest; HTML/CSS/JS sem build; os testes de JS rodam o `<script>` no `node` com DOM falso (`tests/test_painel.py`, helpers `_rodar_js`, `_dados`, `_venda`, `NODE_STUB_EXPLORACAO`).

**Spec:** `docs/superpowers/specs/2026-11-17-exploracao-ordenar-sessoes-fichas-design.md`

## Global Constraints

- Worktree `.claude/worktrees/aba-exploracao`, branch `worktree-aba-exploracao`. Testes: `.venv/bin/python -m pytest -q` (base: 371 passed, 4 skipped). `.venv` é symlink, nunca vai para o git.
- Commits em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Sem dependências novas e sem CDN. A única chamada externa é a API da wiki: `https://elite-dangerous.fandom.com/api.php?action=query&titles=<Página>&prop=pageimages&pithumbsize=400&format=json&origin=*`.
- Nenhuma imagem é baixada para o repositório nem para o zip.
- Textos em PT-BR. Créditos com `mi(n)`. Paleta: fundo `#14100c`, cartão `#1e1813`, borda `#3a2f24`, laranja `#ff8c1a`, texto `#e8dcc8`, rótulo `#9a8b76`. `prefers-reduced-motion` desliga transições.
- `BONUS_PRIMEIRO_REGISTRO` continua sendo a única fonte do ×5.
- Não quebrar o que já existe: os cards mantêm o nó entre polls, o modal aberto é reescrito no lugar, a tabela de preços é desenhada uma vez e a busca sobrevive ao polling. O fechamento por fundo exige mousedown e click no próprio dialog.

## Review Focus

1. **Ordem + polling:** com uma tabela de modal ordenada, o poll de 5 s redesenha a tabela na mesma ordem. → teste na Task 3.
2. **Ordem numérica:** "12,9 mi" tem de vir acima de "5,0 mi" em ordem decrescente, e "—"/vazio sempre no fim. Ordenar pelo texto daria a ordem errada. → teste na Task 3.
3. **Busca + ordenação nos preços:** ordenar não pode desfazer o filtro, e filtrar não pode desfazer a ordem. → teste na Task 3.
4. **Foto da wiki falhando ou lenta** (offline, timeout, página sem imagem, `wiki: null`): a ficha mostra texto e link, sem erro no console e sem travar o modal. Fechar a ficha antes de a foto chegar não pode reabrir nada. → testes na Task 5.
5. **Espécie com nome fora do padrão** ("Amphora plant", "Bark Mounds", espécie desconhecida vinda do journal): o gênero é resolvido ou fica `null`, e um nome sem gênero não vira link. → testes na Task 1 e na Task 5.

---

### Task 1: Dados dos gêneros

**Files:**
- Create: `generos_exobio.json`, `generos_exobio.py`
- Modify: `exploracao.py` (`Historico.__init__`, `_ao_ScanOrganic`, `_vender`, `resumo`), `leitor_exploracao.py` (`iniciar_thread`), `README.md` (lista do zip)
- Test: `tests/test_generos_exobio.py` (novo), `tests/test_exploracao.py`

**Interfaces:**
- Produces:
  - `generos_exobio.json`: `{"generos": {<Gênero>: {"wiki": str|null, "distancia_m": int, "fonte_distancia": "wiki"|"comunidade", "descricao": str}}}`. Ter exatamente os 21 gêneros, com os valores de `wiki`, `distancia_m` e `fonte_distancia` copiados da seção "Dados dos gêneros" do spec. As descrições em PT-BR são escritas pelo implementador, com 1 ou 2 frases sobre o aspecto e onde costuma aparecer, sem copiar da wiki.
  - `generos_exobio.py`:
    - `CAMINHO_PADRAO`;
    - `class Generos(dados: dict)` com `.dados -> dict` (o dicionário `generos`) e `.genero_de(nome_especie: str) -> str | None`: o nome mais longo de gênero que é prefixo do nome normalizado (usar `precos_vista.normalizar`), seguido de fim ou espaço;
    - `carregar_generos(caminho=CAMINHO_PADRAO) -> Generos`.
  - `Historico(precos, generos: Generos | None = None)`. Quando `generos` é `None`, `genero` vale sempre `None` e `resumo()["generos"] == {}`.
  - `resumo()["generos"]` recebe `generos.dados`. Cada item de `resumo()["precos"]` ganha `"genero"`. Cada amostra a bordo e cada vendida ganha `"genero"`, calculado do nome da espécie.
  - `leitor_exploracao.iniciar_thread` passa `generos_exobio.carregar_generos()`.
  - A lista do zip no README ganha `generos_exobio.py` e `generos_exobio.json`. Atualizar `DADOS_DO_CLIENTE` em `tests/test_readme.py` com `generos_exobio.json`, se o teste exigir.

- [ ] **Step 1: Testes que falham** (`tests/test_generos_exobio.py`)

```python
def test_json_tem_os_21_generos_completos():
    g = generos_exobio.carregar_generos().dados
    assert len(g) == 21
    for nome, info in g.items():
        assert info["descricao"].strip() and info["distancia_m"] > 0
        assert info["fonte_distancia"] in ("wiki", "comunidade")
    assert g["Osseus"]["distancia_m"] == 800 and g["Osseus"]["fonte_distancia"] == "wiki"
    assert g["Electricae"]["distancia_m"] == 1000 and g["Electricae"]["fonte_distancia"] == "comunidade"
    assert g["Bark Mounds"]["wiki"] == "Bark Mound" and g["Crystalline Shards"]["wiki"] is None

def test_todas_as_96_especies_da_tabela_tem_genero():
    g = generos_exobio.carregar_generos()
    sem = [n for n, _ in precos_vista.carregar_precos().lista() if g.genero_de(n) is None]
    assert sem == []

def test_genero_de_casos_de_nome():
    g = generos_exobio.carregar_generos()
    assert g.genero_de("Amphora plant") == "Amphora Plant"
    assert g.genero_de("bacterium  ACIES") == "Bacterium"
    assert g.genero_de("Bark Mounds") == "Bark Mounds"
    assert g.genero_de("Especie Nova") is None
    assert g.genero_de("Bacteriumx Algo") is None
```

Em `tests/test_exploracao.py`: `test_resumo_traz_generos_e_genero_nos_itens` (Historico com `Generos({"Bacterium": {...}})`, analisa uma Bacterium Acies e confere `genero == "Bacterium"` em `precos`, a bordo e, depois de uma venda, em vendidas), e `test_sem_generos_resumo_fica_vazio` (`Historico(precos)` resulta em `resumo()["generos"] == {}` e `genero is None`).

- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest -q tests/test_generos_exobio.py tests/test_exploracao.py`. Expected: ImportError/KeyError nos novos.
- [ ] **Step 3: Implementar** conforme as Interfaces.
- [ ] **Step 4: Suíte completa passa:** `.venv/bin/python -m pytest -q`.
- [ ] **Step 5: Commit** com a mensagem "Fichas dos gêneros de exobiologia no resumo da exploração".

---

### Task 2: Sessões no resumo

**Files:** Modify `exploracao.py`. Test `tests/test_exploracao.py`.

**Interfaces:**
- Produces: `resumo()["sessoes"]`, uma lista de até 20 itens `{"sessao": str, "quando": str, "vendido": int, "a_bordo": int}`:
  - entram só as sessões com pelo menos uma coleta (a bordo ou vendida com `sessao` não nula);
  - `quando` é o menor timestamp de coleta da sessão;
  - a lista fica em ordem cronológica crescente por `quando` e guarda as 20 mais recentes;
  - `vendido` soma `valor` das vendidas daquela sessão;
  - `a_bordo` soma `valor_estimado` (pulando `None`) das amostras a bordo daquela sessão.
- Para ter `quando` nas vendidas, `_vender` passa a guardar também `"coletada_em": par["quando"] if par else None`.

- [ ] **Step 1: Testes que falham:**
  - `test_sessoes_somam_por_sessao_de_coleta`: coleta em "s1", venda registrada na sessão "s2"; o valor tem de aparecer em `s1.vendido`, e "s2" não pode aparecer.
  - `test_sessoes_separam_a_bordo_de_vendido`.
  - `test_venda_sem_par_fica_fora_das_sessoes`.
  - `test_sessoes_cortam_nas_20_mais_recentes_em_ordem` (25 sessões com timestamps crescentes; espera as 20 últimas, em ordem).
  - `test_amostra_sem_preco_nao_soma_mas_sessao_aparece`: `a_bordo == 0`.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest -q tests/test_exploracao.py -k sessoes`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Suíte completa passa.**
- [ ] **Step 5: Commit** com a mensagem "Ganhos por sessão de coleta no resumo da exploração".

---

### Task 3: Ordenar tabelas

**Files:** Modify `painel.html`. Test `tests/test_painel.py`.

**Interfaces:**
- Consumes: as tabelas atuais de `conteudoModal` (chaves `a_bordo`, `vendido`, `primeiros`) e de `pintarPrecos` (chave `precos`).
- Produces:
  - `tabelaTexto(cabecalho, linhas, numericas = [], opcoes = {})`. Com `opcoes.chave` (string), a tabela fica ordenável. `opcoes.valores` é opcional: uma matriz paralela a `linhas` com o valor cru de cada célula, usado para ordenar (número, ou `null`/`undefined` para vazio). Sem `valores`, ordena pelo texto.
  - `const ordemTabelas = {}`: `chave -> {coluna: int, desc: bool}`.
  - `function ordenarPor(chave, coluna)`: na primeira vez na coluna, ordena crescente para texto e decrescente para coluna numérica; nas seguintes, inverte. Depois redesenha: para tabelas de modal, chama `preencherModal(modalAberto)`; para `precos`, reordena as linhas do `tbody` existente no lugar, sem recriar o input e sem mexer no `style.display` das linhas.
  - O `th` ordenável recebe a classe `ordenavel` e `onclick`, e a seta ` ▲`/` ▼` é anexada ao texto da coluna ativa. Os testes leem o texto do `th`.
  - Comparação: número contra número; texto com `localeCompare(b, "pt-BR", {sensitivity: "base"})`; valor nulo ou vazio sempre no fim, nos dois sentidos.
  - Passar `valores` crus nas colunas numéricas: Base, Valor, os de preço e Com bônus.
  - CSS: `th.ordenavel { cursor: pointer }`, hover laranja e `:focus-visible`. O `th` recebe `tabIndex = 0` e Enter/Espaço chamam `ordenarPor`. No stub, `addEventListener` já existe.

- [ ] **Step 1: Testes que falham:**
  - `test_ordenar_coluna_numerica_usa_valor_cru`: modal vendido com valores 5_000_000, 12_900_000 e `null`; `ordenarPor('vendido', 2)` deixa a ordem 12,9 / 5,0 / "—" (o vazio fica no fim).
  - `test_segundo_clique_inverte_e_vazio_continua_no_fim`.
  - `test_ordem_sobrevive_ao_polling`: abre o modal, ordena, chama `pintarExploracao(dados)` de novo e a ordem se mantém.
  - `test_ordenar_texto_ignora_acento_e_caixa`.
  - `test_precos_ordenar_mantem_filtro`: filtra "acies", ordena por Base, e as linhas visíveis continuam só as filtradas, agora em ordem.
  - `test_seta_indica_coluna_e_sentido`: o `th` contém "▼" depois de ordenar uma coluna numérica.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest -q tests/test_painel.py -k ordena`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Suíte completa passa.**
- [ ] **Step 5: Commit** com a mensagem "Tabelas da aba Exploração ordenam pelo cabeçalho".

---

### Task 4: Card e gráfico de sessões

**Files:** Modify `painel.html`. Test `tests/test_painel.py`.

**Interfaces:**
- Consumes: `d.sessoes` (Task 2).
- Produces:
  - Card `sessoes` com o rótulo "Sessões" e duas linhas: `${n} sessões` e `melhor: ${mi(max(vendido+a_bordo))}`. Abre o modal. Fica oculto se `d.sessoes` estiver vazio ou ausente, e o mecanismo de chaves de `cartoesFeitos` já recria o conjunto de cards quando isso muda.
  - `TITULO_MODAL.sessoes = "Ganhos por sessão (coleta)"`, e `conteudoModal('sessoes', d)` devolve o gráfico mais uma legenda ("vendido" em cor cheia, "a bordo (estimado)" em cor clara).
  - `function graficoSessoes(sessoes) -> Element (svg)`, criado com `document.createElementNS("http://www.w3.org/2000/svg", ...)`. O stub ganha `createElementNS` que devolve o mesmo nó falso, com `setAttribute` gravando em `attrs`.
    - Uma `<g class="barra">` por sessão, com dois `<rect>`: vendido em `#ff8c1a` e a bordo em `rgba(255,140,26,.35)`, empilhados.
    - Um `<title>` com `${data dd/mm/aaaa} · vendido ${mi} · a bordo ${mi}`, que funciona como tooltip nativo no hover.
    - Rótulo do eixo X `dd/mm` abaixo de cada barra.
    - Escala pelo maior total; com todos os totais zero, as barras ficam com altura 0 e sem divisão por zero.
    - `viewBox` com largura proporcional ao número de sessões e `width="100%"`.
  - CSS: `.barra:hover rect` com brilho (`filter: brightness(1.25)`) e transição respeitando o reduced-motion.

- [ ] **Step 1: Testes que falham:**
  - `test_card_sessoes_aparece_com_dados_e_some_sem`.
  - `test_grafico_uma_barra_por_sessao_com_tooltip`: 3 sessões geram 3 grupos `barra`, e o `<title>` contém "14/11/2026" e o valor `mi`.
  - `test_grafico_tudo_zero_nao_quebra`.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest -q tests/test_painel.py -k sessoes`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Suíte completa passa.**
- [ ] **Step 5: Commit** com a mensagem "Card e gráfico de ganhos por sessão na aba Exploração".

---

### Task 5: Ficha do gênero

**Files:** Modify `painel.html`. Test `tests/test_painel.py`.

**Interfaces:**
- Consumes: `d.generos`, e o campo `genero` em `precos`, `a_bordo.amostras` e `vendido.amostras` (Task 1). Também usa `tabelaTexto` com ordenação (Task 3).
- Produces:
  - Nas tabelas de preços, a bordo e vendido, a célula da espécie vira um `<button class="link-especie">` quando a linha tem `genero`. O texto é o mesmo de hoje e o `onclick` chama `abrirFicha(genero)`. Sem `genero`, a célula continua sendo texto puro. `tabelaTexto` passa a aceitar células que já são `Element`. A ordenação e a busca usam o texto da célula, então a busca precisa ler o `textContent` também de um botão.
  - `let fichaAberta = null; let modalAntesDaFicha = null; const fotosGenero = {};`. Em `fotosGenero`, cada gênero guarda `{estado: "carregando"|"ok"|"falha", url}`.
  - `function abrirFicha(genero)`:
    1. Guarda `modalAberto` em `modalAntesDaFicha` e zera `modalAberto`, para que o polling não reescreva a ficha.
    2. Preenche `#modal-titulo` com o nome do gênero e `#modal-corpo` com a descrição e a linha `Distância mínima entre amostras: ${distancia_m} m (${fonte_distancia === "wiki" ? "fonte: wiki" : "comunidade — confira no Codex"})`.
    3. Mostra a área da foto e o link "ver na wiki", que aponta para `https://elite-dangerous.fandom.com/wiki/${encodeURIComponent(wiki)}` ou, com `wiki` null, para `https://elite-dangerous.fandom.com/wiki/Special:Search?query=${encodeURIComponent(genero)}`. O link usa `target="_blank"` e `rel="noopener"`.
    4. Se veio de um modal, mostra o botão "← voltar", que reabre esse modal.
    5. Chama `showModal()` se o dialog não estiver aberto.
  - `async function carregarFoto(genero, wiki)`:
    - com `wiki` null, marca `falha` sem fazer fetch;
    - se o gênero já está em `fotosGenero`, reusa o resultado;
    - senão faz o `fetch` da URL da API (Global Constraints) com `AbortController` e timeout de 8000 ms, e lê `query.pages[*].thumbnail.source`;
    - ao terminar, só atualiza a tela se `fichaAberta === genero` e o dialog ainda estiver aberto;
    - os estados aparecem como "carregando foto…", `<img alt=genero loading="lazy">` ou "foto indisponível".
  - `fecharModal()` e o evento `close` também zeram `fichaAberta` e `modalAntesDaFicha`.
  - CSS: `.link-especie` sem fundo, sem borda, com `font: inherit`, `color: inherit`, sublinhado pontilhado e cursor de mão; no hover/foco fica laranja. `.ficha-foto img` com `max-width: 100%`, `max-height: 260px`, `border-radius: 6px` e fade-in de 200 ms, respeitando o reduced-motion.

- [ ] **Step 1: Testes que falham.** O stub ganha um `fetch` falso configurável por teste: `globalThis.fetch = async () => ({ json: async () => RESPOSTA })` ou um `fetch` que rejeita. Também ganha um `AbortController` falso.
  - `test_ficha_mostra_descricao_distancia_e_fonte`.
  - `test_ficha_carrega_foto_da_wiki`: depois de `await carregarFoto(...)`, existe um `img` com o src da resposta.
  - `test_ficha_foto_falha_mostra_indisponivel_e_link`.
  - `test_ficha_sem_pagina_wiki_nao_chama_fetch_e_linka_busca`.
  - `test_foto_chega_depois_de_fechar_nao_mexe_no_modal`.
  - `test_voltar_reabre_o_modal_de_origem`.
  - `test_especie_sem_genero_nao_vira_link`.
  - `test_busca_de_precos_continua_funcionando_com_link`.
  - `test_foto_em_cache_nao_busca_de_novo`: conta as chamadas de `fetch`.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest -q tests/test_painel.py -k "ficha or foto or link"`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Suíte completa passa.**
- [ ] **Step 5: Commit** com a mensagem "Ficha do gênero com distância mínima e foto da wiki".

---

### Task 6: Zip do esquadrão

- [ ] **Step 1:** Fazer backup do zip atual (`/home/arthur/Documentos/Estudos/cliente-ed-esquadrao.zip`) no scratchpad.
- [ ] **Step 2:** Atualizar o zip:
  - substituir `cliente-ed/painel.html`, `exploracao.py` e `leitor_exploracao.py` pelas versões do worktree;
  - acrescentar `cliente-ed/generos_exobio.py` e `cliente-ed/generos_exobio.json`;
  - acrescentar na seção "ABA EXPLORAÇÃO" do `LEIA-ME.txt`, mantendo o CRLF e o UTF-8: "Clique no cabeçalho das tabelas para ordenar. Clique no nome de uma espécie para ver a ficha do gênero (foto da wiki, precisa de internet). O card Sessões mostra quanto cada sessão rendeu."
- [ ] **Step 3:** `unzip -l` lista 20 entradas, e `cmp` confirma que os arquivos batem com os do worktree.
