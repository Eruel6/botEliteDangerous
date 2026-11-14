# Aba de exploração e exobiologia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma aba "Exploração" no painel local do cliente que mostra amostras biológicas (a bordo / vendidas), primeiras descobertas e médias, a partir de todos os journals da pasta do jogo.

**Architecture:** `exploracao.Historico` é lógica pura que consome eventos um a um. `leitor_exploracao` lê os journals de forma incremental (offset por arquivo; a carga inicial é só o primeiro ciclo) numa thread própria e publica `Historico.resumo()` em `EstadoCliente`. O painel serve `/exploracao.json` e o `painel.html` ganha duas abas.

**Tech Stack:** Python 3 stdlib (+ `requests` só no script de preços), pytest, HTML/JS puro; testes de JS via `node` como em `tests/test_painel.py`.

**Spec:** `docs/superpowers/specs/2026-11-14-aba-exploracao-design.md`

## Global Constraints

- Rodar testes com `.venv/bin/python -m pytest` (baseline no worktree: 273 passed, 4 skipped — os 4 de `test_paridade.py` dependem de `journals/`, que não existe no worktree). `.venv` é um symlink local: nunca adicionar ao git.
- Nada de rede em tempo de execução do cliente; só o script `scripts/atualizar_precos_vista.py` acessa a internet.
- Nada é enviado ao servidor nem ao Discord.
- A aba funciona com `config.txt` inválido; erro na exploração vira `estado_cliente.registrar_erro("exploração: ...")` e nunca derruba o monitor.
- Bônus nunca aparece como "garantido": valores são `"provavel"`, `"desconhecido"`, `"improvavel"`. Valor com bônus provável = base × 5.
- Só `ScanOrganic` com `ScanType == "Analyse"` gera amostra.
- Nomes de código, mensagens e textos da interface em português, como o resto do projeto. JS monta DOM com `textContent` (nunca `innerHTML` com dado do journal).

## Review Focus

1. Pasta com journals no formato antigo (`Journal.210512183022.01.log`) e novo (`Journal.2026-11-14T094935.01.log`): ordem cronológica tem que ser respeitada, senão vendas/mortes caem antes das coletas → teste em Task 4.
2. Mesmo corpo escaneado de novo numa sessão posterior (agora `WasDiscovered: true` porque **você** vendeu) não pode apagar o "primeiro a descobrir" → teste em Task 2.
3. Última linha do journal pela metade (o jogo ainda escrevendo) não pode ser perdida nem consumida duas vezes → teste em Task 4.
4. `SellOrganicData` com espécie sem par a bordo (coleta anterior ao journal mais antigo) → teste em Task 3.
5. `Analyse` num corpo sem `Scan` no histórico: bônus `"desconhecido"` e nome do corpo com fallback → teste em Task 2.

---

### Task 1: Tabela de preços da Vista Genomics

**Files:**
- Create: `precos_vista.py`
- Create: `precos_vista.json`
- Create: `scripts/atualizar_precos_vista.py`
- Create: `tests/fixtures/vista_genomics.html` (cópia de `/tmp/claude-1000/-home-arthur-Documentos-Estudos-botEliteDangerous/f8f48738-297a-41e6-8be4-8cd10b6c7c5d/scratchpad/site/vista.html`; se não existir mais, baixar de novo com `curl -sL -A "Mozilla/5.0" https://ed-dsn.net/en/vista-genomics-values/`)
- Test: `tests/test_precos_vista.py`

**Interfaces:**
- Produces:
  - `extrair_precos_do_html(html: str) -> dict[str, int]` — nome do site → créditos.
  - `normalizar(nome: str) -> str` — sem acento, minúsculas, espaços colapsados.
  - `class Precos` com `__init__(self, especies: dict[str, int], apelidos: dict[str, str] | None = None)` e `preco(self, nome_localizado: str) -> int | None`.
  - `carregar_precos(caminho: str = CAMINHO_PADRAO) -> Precos`, `CAMINHO_PADRAO` = `precos_vista.json` ao lado do módulo.
  - Formato do JSON: `{"fonte": "https://ed-dsn.net/en/vista-genomics-values/", "atualizado_em": "2026-11-14", "especies": {...}, "apelidos": {}}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_extrai_todas_as_especies_da_pagina_real():
    precos = precos_vista.extrair_precos_do_html(ler_fixture("vista_genomics.html"))
    assert len(precos) == 96
    assert precos["Bacterium Acies"] == 1_000_000
    assert precos["Fonticulua Fluctus"] == 20_000_000
    assert precos["Stratum Tectonicas"] == 19_010_800

def test_preco_casa_sem_diferenciar_acento_e_caixa():
    p = precos_vista.Precos({"Bacterium Acies": 1_000_000})
    assert p.preco("bacterium  ACIES") == 1_000_000

def test_preco_usa_apelido_para_nome_traduzido():
    p = precos_vista.Precos({"Brain Tree": 1_593_700}, {"Árvore Cerebral": "Brain Tree"})
    assert p.preco("Arvore cerebral") == 1_593_700

def test_especie_desconhecida_devolve_none():
    assert precos_vista.Precos({}).preco("Bacterium Nada") is None

def test_json_versionado_carrega_e_tem_as_96_especies():
    p = precos_vista.carregar_precos()
    assert p.preco("Bacterium Acies") == 1_000_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_precos_vista.py -v`
Expected: FAIL (`ModuleNotFoundError: precos_vista`)

- [ ] **Step 3: Implement `precos_vista.py`**

Parse só dentro de `table#tablepress-171`: pares `<td class="column-1">NOME</td><td class="column-2">NN NNN NNN Cr</td>`; `html.unescape` no nome; valor = só os dígitos. `normalizar` via `unicodedata.normalize("NFKD")` removendo combinantes.

- [ ] **Step 4: Implement `scripts/atualizar_precos_vista.py` and generate `precos_vista.json`**

`main()` baixa a URL com `requests` (timeout 30), chama `extrair_precos_do_html`, falha com mensagem clara se vierem menos de 90 espécies, preserva `apelidos` do JSON existente e grava com `ensure_ascii=False, indent=2, sort_keys=True`. Gerar o JSON a partir da fixture (não da rede) para o commit: `.venv/bin/python -c "import json,precos_vista;..."` ou flag `--html <arquivo>` no script.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_precos_vista.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add precos_vista.py precos_vista.json scripts/atualizar_precos_vista.py tests/test_precos_vista.py tests/fixtures/vista_genomics.html
git commit -m "Adiciona a tabela de preços da Vista Genomics"
```

---

### Task 2: Histórico — corpos, primeiras descobertas e amostras a bordo

**Files:**
- Create: `exploracao.py`
- Create: `tests/fixtures/journal_exobio.log` — recorte de `/home/arthur/Documentos/Estudos/botEliteDangerous/journals/Journal.2026-11-14T094935.01.log.txt` (fora do worktree; só leitura) com **só** os eventos `Fileheader`, `Location`, `FSDJump`, `Scan`, `SAAScanComplete`, `Touchdown`, `Disembark`, `CodexEntry`, `ScanOrganic`, `Statistics` (nada de `Commander`, `Friends`, `WingInvite`, `ReceiveText`).
- Test: `tests/test_exploracao.py`

**Interfaces:**
- Consumes: `precos_vista.Precos`.
- Produces:
  - `class Historico` com `__init__(self, precos: Precos)`, `consumir(self, evento: dict, sessao: str) -> None`, `resumo(self) -> dict`.
  - `sessao` é o nome do arquivo de journal de onde veio o evento.
  - Forma de `resumo()` (Task 3 completa os campos `vendido`, `perdido`, `medias`):

```python
{
  "a_bordo": {"amostras": [AMOSTRA], "total_base": int, "total_com_bonus": int,
              "sistemas_exploracao": int, "corpos_exploracao": int},
  "vendido": {"amostras": [VENDIDA], "total": int, "exploracao_total": int},
  "perdido": {"amostras": int, "sistemas": int},
  "medias": {"por_amostra": int | None, "por_planeta": int | None, "por_sessao": int | None},
  "primeiros": {"sistemas_descobertos": int, "corpos_descobertos": int,
                "mapeados": int, "pisados": int,
                "corpos": [{"corpo": str, "sistema": str, "descobriu": bool,
                            "mapeou": bool, "pisou": bool}]},
  "carreira": dict | None,   # último Statistics["Exobiology"]
}
# AMOSTRA = {"especie": str, "variante": str, "corpo": str, "sistema": str,
#            "quando": str, "preco_base": int | None,
#            "bonus": "provavel" | "desconhecido" | "improvavel",
#            "valor_estimado": int | None, "sessao": str}
```

Regras desta task:
- Corpo = chave `(SystemAddress, BodyID)`. As flags `WasDiscovered/WasMapped/WasFootfalled` vêm do **primeiro** `Scan` visto do corpo e nunca são sobrescritas.
- Nome do sistema por `SystemAddress`: de `FSDJump`/`Location`/`Scan` (`StarSystem`).
- `mapeou` = houve `SAAScanComplete` do corpo; `pisou` = houve `Disembark` com `OnPlanet: true` no corpo.
- `primeiros.corpos` lista só corpos com algum `True`, onde `descobriu = not WasDiscovered`, `mapeou = mapeou and not WasMapped`, `pisou = pisou and not WasFootfalled`. Os contadores contam esses `True`.
- `sistemas_descobertos`: sistemas cujo `Scan` com `DistanceFromArrivalLS == 0` veio com `WasDiscovered: false`.
- Amostra a bordo: `bonus = "provavel"` se o corpo tem `Scan` com `WasFootfalled: false`, `"improvavel"` se `true`, `"desconhecido"` sem `Scan`. `valor_estimado = preco_base * 5` se provável, `preco_base` caso contrário, `None` sem preço. Corpo sem nome → `f"corpo {BodyID}"`.
- Dados de exploração a bordo: sistemas (por nome) com pelo menos um `Scan` desde a última venda/morte; `corpos_exploracao` = corpos escaneados nesses sistemas.

- [ ] **Step 1: Write the failing tests**

```python
def test_journal_real_gera_uma_amostra_a_bordo_com_bonus_provavel():
    r = historico_da_fixture("journal_exobio.log").resumo()
    [a] = r["a_bordo"]["amostras"]
    assert a["especie"] == "Bacterium Acies"
    assert a["corpo"] == "Plio Eurl IX-Z b14-0 B 1"
    assert a["sistema"] == "Plio Eurl IX-Z b14-0"
    assert a["quando"] == "2026-11-14T13:42:14Z"
    assert (a["preco_base"], a["bonus"], a["valor_estimado"]) == (1_000_000, "provavel", 5_000_000)
    assert r["a_bordo"]["total_base"] == 1_000_000
    assert r["a_bordo"]["total_com_bonus"] == 5_000_000

def test_log_e_sample_nao_geram_amostra(): ...  # só os 3 primeiros ScanOrganic → 0 amostras

def test_journal_real_marca_b1_como_descoberto_mapeado_e_pisado():
    p = historico_da_fixture("journal_exobio.log").resumo()["primeiros"]
    b1 = next(c for c in p["corpos"] if c["corpo"] == "Plio Eurl IX-Z b14-0 B 1")
    assert (b1["descobriu"], b1["mapeou"], b1["pisou"]) == (True, True, True)
    assert p["sistemas_descobertos"] == 0          # estrelas A e B já descobertas
    assert p["corpos_descobertos"] == 19

def test_scan_posterior_nao_apaga_primeira_descoberta():
    # Scan com WasDiscovered False e depois o mesmo corpo com WasDiscovered True
    # → continua descobriu=True

def test_amostra_em_corpo_sem_scan_tem_bonus_desconhecido_e_nome_de_fallback():
    # só ScanOrganic Analyse com Body 7 → corpo == "corpo 7", bonus == "desconhecido",
    # valor_estimado == preco_base

def test_amostra_em_corpo_ja_pisado_tem_bonus_improvavel(): ...

def test_especie_sem_preco_fica_sem_valor_e_fora_dos_totais(): ...

def test_carreira_vem_do_ultimo_statistics():
    r = historico_da_fixture("journal_exobio.log").resumo()
    assert r["carreira"]["Organic_Data_Profits"] == 439_542_900
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_exploracao.py -v`
Expected: FAIL (`ModuleNotFoundError: exploracao`)

- [ ] **Step 3: Implement `Historico` in `exploracao.py`** following the rules above. `consumir` despacha por `evento.get("event")`; evento desconhecido é ignorado.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_exploracao.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add exploracao.py tests/test_exploracao.py tests/fixtures/journal_exobio.log
git commit -m "Adiciona o histórico de exploração: amostras a bordo e primeiras descobertas"
```

---

### Task 3: Vendas, morte e médias

**Files:**
- Modify: `exploracao.py`
- Test: `tests/test_exploracao.py`

**Interfaces:**
- Consumes: `Historico` da Task 2.
- Produces: os campos `vendido`, `perdido`, `medias` de `resumo()`, com

```python
# VENDIDA = {"especie": str, "variante": str, "corpo": str | None, "sistema": str | None,
#            "quando": str, "valor": int, "bonus_pago": int,
#            "previsao": "provavel" | "desconhecido" | "improvavel" | None,
#            "acertou": bool | None}
```

Regras:
- `SellOrganicData`: para cada item de `BioData`, remove a amostra a bordo **mais antiga** com o mesmo `Species` (id interno, guardado na amostra desde a Task 2 como campo privado ou junto). `valor = Value + Bonus`, `bonus_pago = Bonus`. `previsao` = o `bonus` da amostra casada; `acertou = (Bonus > 0) == (previsao == "provavel")`, ou `None` se a previsão era `"desconhecido"` ou não houve par. Sem par: `corpo`, `sistema`, `previsao`, `acertou` = `None`.
- `vendido.total` = soma dos `valor`. `vendido.exploracao_total` = soma de `TotalEarnings` de `SellExplorationData` e `MultiSellExplorationData`.
- `SellExplorationData.Systems[]` e `MultiSellExplorationData.Discovered[].SystemName` tiram esses sistemas da exploração a bordo.
- `Died`: amostras a bordo → `perdido.amostras += n`; sistemas a bordo → `perdido.sistemas += n`; ambos esvaziados.
- Médias (créditos inteiros, arredondados; `None` sem dados), sobre amostras **a bordo com `valor_estimado`** + **vendidas** (perdidas ficam fora), valor de cada uma = `valor_estimado` ou `valor`:
  - `por_amostra` = soma / quantidade.
  - `por_planeta` = soma das que têm corpo / nº de corpos distintos.
  - `por_sessao` = soma das que têm sessão de coleta / nº de sessões distintas (a vendida herda a `sessao` da amostra casada).

- [ ] **Step 1: Write the failing tests** (fixtures sintéticas em código, eventos como dicts)

```python
def test_venda_tira_a_amostra_de_bordo_e_registra_o_valor_real():
    h = historico_com_analyse("Bacterium Acies", corpo_nao_pisado=True)
    h.consumir(venda_organica([("$Codex_Ent_Bacterial_04_Name;", "Bacterium Acies", 1_000_000, 4_000_000)]), "s2")
    r = h.resumo()
    assert r["a_bordo"]["amostras"] == []
    [v] = r["vendido"]["amostras"]
    assert (v["valor"], v["bonus_pago"], v["previsao"], v["acertou"]) == (5_000_000, 4_000_000, "provavel", True)

def test_venda_casa_pela_amostra_mais_antiga_da_mesma_especie(): ...
def test_venda_sem_par_entra_sem_planeta():
    # Review Focus 4 → corpo None, previsao None, acertou None, total conta o valor
def test_morte_perde_amostras_e_dados_de_exploracao_a_bordo(): ...
def test_venda_de_exploracao_tira_os_sistemas_de_bordo_e_soma_o_total(): ...  # Sell e MultiSell
def test_medias_ignoram_perdidas_e_amostras_sem_preco(): ...
def test_medias_sem_dados_sao_none(): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_exploracao.py -v`
Expected: the new tests FAIL

- [ ] **Step 3: Implement** vendas, morte e médias em `exploracao.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_exploracao.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add exploracao.py tests/test_exploracao.py
git commit -m "Separa amostras vendidas e perdidas e calcula as médias"
```

---

### Task 4: Leitor incremental e thread de exploração

**Files:**
- Create: `leitor_exploracao.py`
- Modify: `estado.py`
- Test: `tests/test_leitor_exploracao.py`, `tests/test_estado.py`

**Interfaces:**
- Consumes: `exploracao.Historico`, `precos_vista.carregar_precos`, `ed_parser.PASTA_JOURNAL_PADRAO`, `monitor.INTERVALO_CHECAGEM` (importar o valor 60 de `monitor` é aceitável; se criar import circular, duplicar a constante com comentário).
- Produces:
  - `ordem_do_journal(caminho: str) -> str` — chave ISO `"YYYY-MM-DDTHHMMSS.parte"` para os dois formatos de nome: novo `Journal.2026-11-14T094935.01.log` e antigo `Journal.210512183022.01.log` (`YYMMDDHHMMSS`, ano 20YY). Nome fora dos dois padrões vai para o começo (`""`).
  - `class LeitorExploracao` com `__init__(self, historico: Historico, pasta: str | None = None)` e `ciclo(self) -> None`: lista `Journal.*.log`, ordena por `ordem_do_journal`, e para cada arquivo lê a partir do offset guardado (`dict[caminho, int]`, em bytes) só até o último `b"\n"`; cada linha é decodificada em UTF-8, `json.loads` (linha inválida pulada) e passada a `historico.consumir(evento, os.path.basename(caminho))`. A carga inicial é o primeiro `ciclo()`.
  - `iniciar_thread(estado_cliente, pasta: str | None = None, intervalo: int = 60) -> threading.Thread` — daemon; laço: `ciclo()`, `estado_cliente.registrar_exploracao(historico.resumo())`, dorme; exceção → `estado_cliente.registrar_erro(f"exploração: {e}")` e segue.
  - `EstadoCliente.registrar_exploracao(self, resumo: dict) -> None` e `EstadoCliente.exploracao(self) -> dict` = `{"carregando": True}` até o primeiro registro, depois `{"carregando": False, **resumo}`.

- [ ] **Step 1: Write the failing tests** (pasta em `tmp_path`)

```python
def test_ordena_formatos_antigo_e_novo_cronologicamente():
    nomes = ["Journal.2026-11-14T094935.01.log", "Journal.210512183022.01.log",
             "Journal.2025-05-20T141829.01.log", "Journal.210512183022.02.log"]
    assert sorted(nomes, key=leitor_exploracao.ordem_do_journal) == [
        "Journal.210512183022.01.log", "Journal.210512183022.02.log",
        "Journal.2025-05-20T141829.01.log", "Journal.2026-11-14T094935.01.log"]

def test_ciclo_consome_eventos_de_varios_arquivos_em_ordem(tmp_path): ...
def test_segundo_ciclo_so_le_linhas_novas(tmp_path):
    # acrescenta 1 linha entre ciclos → historico falso recebe exatamente 1 evento novo
def test_linha_incompleta_no_fim_fica_para_o_proximo_ciclo(tmp_path):
    # Review Focus 3: escreve '{"event":"Scan"' sem \n, ciclo, completa a linha, ciclo
    # → evento consumido exatamente uma vez
def test_linha_invalida_e_pulada(tmp_path): ...
def test_pasta_vazia_nao_falha(tmp_path): ...
```

Em `tests/test_estado.py`:

```python
def test_exploracao_comeca_carregando_e_depois_traz_o_resumo():
    e = estado.EstadoCliente()
    assert e.exploracao() == {"carregando": True}
    e.registrar_exploracao({"a_bordo": {}})
    assert e.exploracao() == {"carregando": False, "a_bordo": {}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_leitor_exploracao.py tests/test_estado.py -v`
Expected: new tests FAIL

- [ ] **Step 3: Implement `leitor_exploracao.py` and the two methods in `estado.py`** (sob o `self._lock` existente).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_leitor_exploracao.py tests/test_estado.py -v`
Expected: all passed

- [ ] **Step 5: Measure initial load on real data**

Run: `.venv/bin/python -c "import time,exploracao,precos_vista,leitor_exploracao as l; h=exploracao.Historico(precos_vista.carregar_precos()); t=time.time(); l.LeitorExploracao(h,'/home/arthur/Documentos/Estudos/botEliteDangerous/journals').ciclo(); print(round(time.time()-t,2),'s'); print(h.resumo()['a_bordo']['amostras'])"`
Expected: imprime o tempo; a amostra Bacterium Acies **não** aparece porque `journals/` tem o arquivo como `.log.txt` (fora do glob) — renomear uma cópia temporária para `.log` em `tmp_path` se quiser ver a amostra. Anotar o tempo no commit.

- [ ] **Step 6: Commit**

```bash
git add leitor_exploracao.py estado.py tests/test_leitor_exploracao.py tests/test_estado.py
git commit -m "Lê os journals de forma incremental para a aba de exploração"
```

---

### Task 5: Rota, aba no painel e partida no cliente

**Files:**
- Modify: `painel.py` (rota em `do_GET`, perto da linha 21)
- Modify: `painel.html`
- Modify: `cliente.py`
- Test: `tests/test_painel.py`, `tests/test_cliente.py`

**Interfaces:**
- Consumes: `EstadoCliente.exploracao()`, `leitor_exploracao.iniciar_thread`.
- Produces:
  - `GET /exploracao.json` → `json.dumps(estado_cliente.exploracao(), ensure_ascii=False)`.
  - `cliente.main(aguardar=..., iniciar_exploracao=leitor_exploracao.iniciar_thread)` — chama `iniciar_exploracao(estado_cliente)` logo depois de `painel.iniciar_painel(...)`, **nos dois ramos** (config válida e inválida).
  - Em `painel.html`: botões de aba "Colonização" / "Exploração" (conteúdo atual dentro de um contêiner da aba Colonização, sem mudanças nele); função global `pintarExploracao(d)` que preenche a aba conforme o esboço da spec (blocos A bordo, Vendido, Médias, Primeiro a..., Carreira); `carregando: true` mostra "lendo os journals…". Créditos formatados como `"5,0 mi"` (milhões com uma casa, vírgula decimal). Bônus exibido como "provável", "desconhecido", "improvável"; vendida mostra "previsão certa"/"previsão errada" quando `acertou` não é `null`. `atualizar()` também busca `/exploracao.json` e chama `pintarExploracao`; falha nessa busca não afeta a aba de colonização.

- [ ] **Step 1: Write the failing tests**

```python
def test_exploracao_json_devolve_o_estado_de_exploracao(servidor_no_ar):
    base, e = servidor_no_ar
    assert json.loads(buscar(f"{base}/exploracao.json")[1]) == {"carregando": True}

def test_a_pagina_tem_as_duas_abas():
    # "Colonização" e "Exploração" no HTML, e a função pintarExploracao

def test_pintar_exploracao_renderiza_amostra_a_bordo_e_primeiros():
    # padrão node de test_pintar_renderiza_a_secao_de_compras_funcionalmente:
    # resumo com 1 amostra Bacterium Acies (provavel, 5_000_000) e B 1 descoberto/mapeado/pisado
    # → texto contém "Bacterium Acies", "provável", "5,0 mi", "Plio Eurl IX-Z b14-0 B 1"

def test_pintar_exploracao_mostra_carregando(): ...  # {"carregando": true} → "lendo os journals"
```

Em `tests/test_cliente.py`:

```python
def test_config_invalida_ainda_inicia_a_exploracao(monkeypatch, capsys):
    # mesmo arranjo do teste existente; main(aguardar=interromper, iniciar_exploracao=falso)
    # → falso foi chamado com o mesmo estado entregue ao painel
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_painel.py tests/test_cliente.py -v`
Expected: new tests FAIL

- [ ] **Step 3: Implement** a rota, as abas e `pintarExploracao` em `painel.html`, e o parâmetro em `cliente.main`. Se o teste node existente que corta o script em `async function atualizar` quebrar, mantenha `pintarExploracao` **antes** de `atualizar`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: todos passam (289 + os novos)

- [ ] **Step 5: Check the panel by eye**

Subir só o painel com um estado preenchido a partir de `tests/fixtures/journal_exobio.log` (`painel.iniciar_painel` + `leitor_exploracao` numa pasta temporária com a fixture copiada como `Journal.2026-11-14T094935.01.log`), abrir `http://127.0.0.1:<porta>`, conferir as duas abas e que a de colonização segue igual.

- [ ] **Step 6: Commit**

```bash
git add painel.py painel.html cliente.py tests/test_painel.py tests/test_cliente.py
git commit -m "Adiciona a aba de exploração ao painel"
```
