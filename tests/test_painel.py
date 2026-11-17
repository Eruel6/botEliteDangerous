# tests/test_painel.py
import json
import os
import re
import shutil
import subprocess
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
    e.registrar_envio(200)
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


def test_pintar_renderiza_a_secao_de_compras_funcionalmente():
    """Testa que pintar() renderiza corretamente as sugestões de compra."""
    node_bin = shutil.which("node") or shutil.which("nodejs")
    if not node_bin:
        pytest.skip("node não encontrado")

    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()

    # Extrai o script, removendo as funções async e setInterval que não queremos executar
    match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert match, "Script não encontrado no HTML"
    script_full = match.group(1)

    # Remove as últimas linhas que contêm async function atualizar e setInterval
    script_lines = script_full.split('\n')
    # Encontra onde começa a função async
    async_start = None
    for i, line in enumerate(script_lines):
        if 'async function atualizar' in line:
            async_start = i
            break

    if async_start:
        script = '\n'.join(script_lines[:async_start])
    else:
        script = script_full

    # DOM stub que rastreia renderização
    dom_setup = """
const elements = {};
const innerHTML_forbidden = new Error("innerHTML não é permitido");

function checkInnerHTML(obj) {
  try {
    Object.defineProperty(obj, 'innerHTML', {
      set: function() { throw innerHTML_forbidden; }
    });
  } catch (e) {}
}

const document = {
  getElementById: function(id) {
    if (!elements[id]) {
      elements[id] = {
        id: id,
        children: [],
        textContent: undefined,
        className: undefined,
        style: {},
        replaceChildren: function() {
          this.children = [];
        },
        appendChild: function(child) {
          this.children.push(child);
        },
        insertRow: function() {
          const row = {
            cells: [],
            insertCell: function() {
              const cell = {
                colSpan: undefined,
                className: undefined,
                textContent: undefined
              };
              this.cells.push(cell);
              return cell;
            }
          };
          this.children.push(row);
          return row;
        }
      };
      checkInnerHTML(elements[id]);
    }
    return elements[id];
  },
  createElement: function(tag) {
    const el = {
      tag: tag,
      children: [],
      textContent: undefined,
      className: undefined,
      style: {},
      appendChild: function(child) {
        this.children.push(child);
      }
    };
    checkInnerHTML(el);
    return el;
  }
};

function coletarDados(elem, depth = 0) {
  if (!elem) return [];
  let resultado = [];
  if (elem.textContent) resultado.push(elem.textContent);
  if (elem.className) resultado.push('[classe: ' + elem.className + ']');
  if (elem.children && elem.children.length) {
    for (const child of elem.children) {
      resultado = resultado.concat(coletarDados(child, depth + 1));
    }
  }
  return resultado;
}
"""

    # Teste 1: vazio
    teste1_dados = {
        "ultimo_status_http": 200,
        "ultimo_envio_ok": None,
        "ultima_leitura": None,
        "journal_atual": None,
        "instalacoes": [],
        "erros": [],
        "compras": []
    }

    script_teste1 = dom_setup + "\n" + script + "\n" + "pintar(" + json.dumps(teste1_dados) + ");\n" + \
        "const resultado1 = coletarDados(elements['compras']);\n" + \
        "console.log(resultado1.join('|'));\n"

    result = subprocess.run(
        [node_bin],
        input=script_teste1,
        capture_output=True,
        text=True,
        timeout=5
    )

    if "innerHTML não é permitido" in result.stderr:
        pytest.fail("innerHTML foi atribuído no código")
    if result.returncode != 0:
        pytest.fail(f"Erro teste 1: {result.stderr}")

    # Verifica que a mensagem vazia aparece
    assert "nada faltando" in result.stdout, f"Teste 1 - mensagem vazia não encontrada: {result.stdout}"

    # Teste 2: com estações, incluindo uma com carrier
    teste2_dados = {
        "ultimo_status_http": 200,
        "ultimo_envio_ok": None,
        "ultima_leitura": None,
        "journal_atual": None,
        "instalacoes": [],
        "erros": [],
        "compras": [
            {
                "material": "Ferro",
                "faltando": "100 t",
                "consultavel": True,
                "desatualizado": False,
                "estacoes": [
                    {
                        "nome": "Estação A",
                        "sistema": "Sirius",
                        "distancia_ly": 8.7,
                        "distancia_ls": 100,
                        "estoque": 500,
                        "preco": 250,
                        "carrier": False
                    },
                    {
                        "nome": "Carrier B",
                        "sistema": "Sirius",
                        "distancia_ly": 8.7,
                        "distancia_ls": 200,
                        "estoque": 1000,
                        "preco": 240,
                        "carrier": True
                    }
                ]
            }
        ]
    }

    script_teste2 = dom_setup + "\n" + script + "\n" + "pintar(" + json.dumps(teste2_dados) + ");\n" + \
        "const resultado2 = coletarDados(elements['compras']);\n" + \
        "console.log(resultado2.join('|'));\n"

    result = subprocess.run(
        [node_bin],
        input=script_teste2,
        capture_output=True,
        text=True,
        timeout=5
    )

    if "innerHTML não é permitido" in result.stderr:
        pytest.fail("innerHTML foi atribuído no código")
    if result.returncode != 0:
        pytest.fail(f"Erro teste 2: {result.stderr}")

    # Verifica que ambas estações aparecem
    assert "Estação A" in result.stdout, f"Teste 2 - Estação A não encontrada: {result.stdout}"
    assert "Carrier B" in result.stdout, f"Teste 2 - Carrier B não encontrada: {result.stdout}"
    assert "🛸" in result.stdout, f"Teste 2 - emoji carrier não encontrado: {result.stdout}"

    # Teste 3: consultavel = false
    teste3_dados = {
        "ultimo_status_http": 200,
        "ultimo_envio_ok": None,
        "ultima_leitura": None,
        "journal_atual": None,
        "instalacoes": [],
        "erros": [],
        "compras": [
            {
                "material": "Ouro",
                "faltando": "50 t",
                "consultavel": False,
                "desatualizado": False,
                "estacoes": []
            }
        ]
    }

    script_teste3 = dom_setup + "\n" + script + "\n" + "pintar(" + json.dumps(teste3_dados) + ");\n" + \
        "const resultado3 = coletarDados(elements['compras']);\n" + \
        "console.log(resultado3.join('|'));\n"

    result = subprocess.run(
        [node_bin],
        input=script_teste3,
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode != 0:
        pytest.fail(f"Erro teste 3: {result.stderr}")

    assert "sem dados de compra" in result.stdout, f"Teste 3 - mensagem consultavel false não encontrada: {result.stdout}"

    # Teste 4: desatualizado = true (API falhou)
    teste4_dados = {
        "ultimo_status_http": 200,
        "ultimo_envio_ok": None,
        "ultima_leitura": None,
        "journal_atual": None,
        "instalacoes": [],
        "erros": [],
        "compras": [
            {
                "material": "Platina",
                "faltando": "75 t",
                "consultavel": True,
                "desatualizado": True,
                "estacoes": []
            }
        ]
    }

    script_teste4 = dom_setup + "\n" + script + "\n" + "pintar(" + json.dumps(teste4_dados) + ");\n" + \
        "const resultado4 = coletarDados(elements['compras']);\n" + \
        "console.log(resultado4.join('|'));\n"

    result = subprocess.run(
        [node_bin],
        input=script_teste4,
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode != 0:
        pytest.fail(f"Erro teste 4: {result.stderr}")

    assert "não consegui consultar agora" in result.stdout, f"Teste 4 - mensagem API falha não encontrada: {result.stdout}"
    assert "nada dentro de 50 ly" not in result.stdout, f"Teste 4 - mensagem errada quando API falhou: {result.stdout}"
    # Sem "quando" (payload antigo, ou nunca houve sucesso): cai no rótulo genérico.
    assert "dados antigos" in result.stdout, f"Teste 4 - rótulo genérico ausente: {result.stdout}"

    # Teste 5: desatualizado = true e com a hora do último dado bom
    teste5_dados = {
        "ultimo_status_http": 200,
        "ultimo_envio_ok": None,
        "ultima_leitura": None,
        "journal_atual": None,
        "instalacoes": [],
        "erros": [],
        "compras": [
            {
                "material": "Paládio",
                "faltando": "40 t",
                "consultavel": True,
                "desatualizado": True,
                "quando": "2026-09-05T14:32:00Z",
                "estacoes": []
            }
        ]
    }

    script_teste5 = dom_setup + "\n" + script + "\n" + "pintar(" + json.dumps(teste5_dados) + ");\n" + \
        "const resultado5 = coletarDados(elements['compras']);\n" + \
        "console.log(resultado5.join('|'));\n"

    result = subprocess.run(
        [node_bin],
        input=script_teste5,
        capture_output=True,
        text=True,
        timeout=5,
        env={**os.environ, "TZ": "UTC"},
    )

    if result.returncode != 0:
        pytest.fail(f"Erro teste 5: {result.stderr}")

    assert "dados de 14:32" in result.stdout, f"Teste 5 - hora do dado antigo ausente: {result.stdout}"


def test_exploracao_json_devolve_o_estado_de_exploracao(servidor_no_ar):
    base, _ = servidor_no_ar

    status, corpo = buscar(f"{base}/exploracao.json")

    assert status == 200
    assert json.loads(corpo) == {"carregando": True}


def test_a_pagina_tem_as_duas_abas():
    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()

    assert "Colonização" in html
    assert "Exploração" in html
    assert "function pintarExploracao" in html


NODE_STUB_EXPLORACAO = """
const elements = {};
function novo(tag) {
  return {
    set id(v) { elements[v] = this; },
    tag: tag, children: [], _t: undefined, className: undefined, style: {},
    get textContent() {
      return this._t !== undefined ? this._t
        : (this.children.length ? this.children.map(c => c.textContent).join("") : undefined);
    },
    set textContent(v) { this._t = v; this.children = []; },
    scrollTop: 0, open: false,
    replaceChildren(...novos) { this.children = novos; },
    appendChild(c) { this.children.push(c); },
    showModal() { this.open = true; },
    close() { this.open = false; },
    addEventListener() {},
    attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; },
    focus() { this.focado = true; document.activeElement = this; },
    contains(n) { return n === this || this.children.some(c => c.contains && c.contains(n)); },
  };
}
const document = {
  activeElement: null,
  getElementById(id) { return elements[id] || (elements[id] = novo(id)); },
  createElement: novo,
  createElementNS(ns, tag) { return novo(tag); },
};
class AbortController {
  constructor() { this.signal = { aborted: false }; }
  abort() { this.signal.aborted = true; }
}
function textos(el) {
  let r = [];
  if (el._t) r.push(el._t);
  for (const c of el.children || []) r = r.concat(textos(c));
  return r;
}
function linhasVisiveis() {
  const r = [];
  (function andar(el) {
    if (el.tag === "tr" && el.style.display !== "none") {
      const td = (el.children || []).find(c => c.tag === "td");
      if (td) r.push(td.textContent);
    }
    for (const c of el.children || []) andar(c);
  })(elements["exploracao-precos"]);
  return r;
}
"""


def _rodar_js(programa_extra, dados=None, timeout=5):
    """Roda o script do painel com o DOM falso; pinta `dados` (se houver) e
    depois executa `programa_extra`. Devolve o stdout."""
    node_bin = shutil.which("node") or shutil.which("nodejs")
    if not node_bin:
        pytest.skip("node não encontrado")
    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
    script = script.split("async function atualizar")[0]
    pintar = f"pintarExploracao({json.dumps(dados)});\n" if dados is not None else ""
    programa = NODE_STUB_EXPLORACAO + script + pintar + programa_extra + "\n"
    r = subprocess.run([node_bin], input=programa, capture_output=True,
                       text=True, timeout=timeout)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _rodar_pintar_exploracao(dados, extra=""):
    return _rodar_js("console.log(textos(elements['exploracao-cartoes']).join('|'));\n"
                     + extra, dados)


def _dados(**mudancas):
    """Resumo de exploração completo e vazio; `mudancas` troca blocos inteiros."""
    base = {
        "carregando": False,
        "a_bordo": {"amostras": [], "total_base": 0, "total_com_bonus": 0,
                    "provaveis_quantidade": 0, "provaveis_base": 0,
                    "provaveis_com_bonus": 0,
                    "sistemas_exploracao": 0, "corpos_exploracao": 0},
        "vendido": {"amostras": [], "quantidade": 0, "total": 0, "exploracao_total": 0,
                    "multiplicador_observado": None},
        "perdido": {"amostras": 0, "sistemas": 0},
        "medias": {"por_amostra": None, "por_planeta": None, "por_sessao": None},
        "primeiros": {"sistemas_descobertos": 0, "corpos_descobertos": 0,
                      "mapeados": 0, "pisados": 0, "total_corpos": 0, "corpos": []},
        "carreira": None,
        "multiplicador": 5,
        "precos": [],
        "precos_atualizado_em": None,
        "sessoes": [],
    }
    base.update(mudancas)
    return base


def _venda(especie="Aleoida Arcus", **mudancas):
    v = {"especie": especie, "variante": "v", "corpo": "A 1", "sistema": "A",
         "quando": "t", "valor": 7_000_000, "bonus_pago": 0, "previsao": None,
         "acertou": None, "sessao": None}
    v.update(mudancas)
    return v


def _textos_modal(chave, dados):
    return _rodar_js(f"console.log(textos(conteudoModal('{chave}', {json.dumps(dados)})).join('|'));")


def test_pintar_exploracao_renderiza_amostra_a_bordo_e_primeiros():
    amostra = {"especie": "Bacterium Acies", "especie_id": "x", "variante": "Água-marinha",
               "corpo": "Plio Eurl IX-Z b14-0 B 1", "sistema": "Plio Eurl IX-Z b14-0",
               "quando": "2026-11-14T10:00:00Z", "preco_base": 5_000_000,
               "bonus": "provavel", "valor_estimado": 20_000_000, "sessao": 1}
    dados = _dados(
        a_bordo={"amostras": [amostra], "total_base": 5_000_000,
                 "total_com_bonus": 20_000_000, "provaveis_quantidade": 1,
                 "provaveis_base": 5_000_000, "provaveis_com_bonus": 25_000_000,
                 "sistemas_exploracao": 1, "corpos_exploracao": 3},
        medias={"por_amostra": 5_000_000, "por_planeta": None, "por_sessao": None},
        primeiros={"sistemas_descobertos": 0, "corpos_descobertos": 1,
                   "mapeados": 1, "pisados": 1, "total_corpos": 1,
                   "corpos": [{"corpo": "Plio Eurl IX-Z b14-0 B 1",
                               "sistema": "Plio Eurl IX-Z b14-0",
                               "descobriu": True, "mapeou": True, "pisou": True}]})

    cartoes = _rodar_pintar_exploracao(dados)
    a_bordo = _textos_modal("a_bordo", dados)
    primeiros = _textos_modal("primeiros", dados)

    assert "A bordo" in cartoes and "por amostra 5,0 mi" in cartoes
    assert "Bacterium Acies" in a_bordo
    assert "provável" in a_bordo
    assert "5,0 mi" in a_bordo
    assert "Plio Eurl IX-Z b14-0 B 1" in primeiros


def test_pintar_exploracao_mostra_previsao_da_venda_e_a_carreira():
    dados = _dados(
        vendido={"amostras": [_venda(previsao="provavel", acertou=False, sessao=1)],
                 "quantidade": 1, "total": 7_000_000, "exploracao_total": 0,
                 "multiplicador_observado": None},
        carreira={"Organic_Data": 27, "Organic_Data_Profits": 439_500_000,
                  "First_Logged": 25})

    saida = _rodar_pintar_exploracao(dados)
    vendido = _textos_modal("vendido", dados)

    assert "Aleoida Arcus" in vendido
    assert "previsão errada" in vendido
    assert "439,5 mi" in saida
    assert "25 primeiras descobertas" in saida


def test_pintar_exploracao_mostra_carregando():
    saida = _rodar_pintar_exploracao({"carregando": True})

    assert "lendo os journals" in saida


def test_pintar_exploracao_avisa_quando_a_lista_foi_cortada():
    corpo = {"corpo": "A 1", "sistema": "A", "descobriu": True, "mapeou": False, "pisou": False}
    dados = _dados(
        vendido={"amostras": [_venda()] * 50, "quantidade": 73, "total": 73,
                 "exploracao_total": 0, "multiplicador_observado": None},
        primeiros={"sistemas_descobertos": 0, "corpos_descobertos": 61,
                   "mapeados": 0, "pisados": 0, "total_corpos": 61,
                   "corpos": [corpo] * 50})

    assert "73 amostras" in _rodar_pintar_exploracao(dados)
    assert "mostrando 50 de 73" in _textos_modal("vendido", dados)
    assert "mostrando 50 de 61" in _textos_modal("primeiros", dados)


def test_pintar_exploracao_nao_avisa_corte_quando_cabe_tudo():
    dados = _dados(primeiros={
        "sistemas_descobertos": 0, "corpos_descobertos": 1, "mapeados": 0,
        "pisados": 0, "total_corpos": 1,
        "corpos": [{"corpo": "A 1", "sistema": "A", "descobriu": True,
                    "mapeou": False, "pisou": False}]})

    assert "mostrando" not in _rodar_pintar_exploracao(dados)
    assert "mostrando" not in _textos_modal("primeiros", dados)


def test_card_a_bordo_mostra_provaveis_com_e_sem_multiplicador():
    dados = _dados(a_bordo={
        "amostras": [], "total_base": 7_000_000, "total_com_bonus": 7_000_000,
        "provaveis_quantidade": 1, "provaveis_base": 5_000_000,
        "provaveis_com_bonus": 25_000_000,
        "sistemas_exploracao": 0, "corpos_exploracao": 0})

    saida = _rodar_pintar_exploracao(dados)

    assert "prováveis (1): 5,0 mi → 25,0 mi" in saida
    assert "×5, estimado" in saida


def test_card_mostra_multiplicador_observado_quando_diverge():
    dados = _dados(vendido={"amostras": [], "quantidade": 0, "total": 0,
                            "exploracao_total": 0, "multiplicador_observado": 2.0})

    saida = _rodar_pintar_exploracao(dados)

    assert "com bônus (×5, observado ×2,0)" in saida
    assert "bônus observado ×2,0" in saida


def test_card_a_bordo_arredonda_observado_antes_de_comparar():
    dados = _dados(vendido={"amostras": [], "quantidade": 0, "total": 0,
                            "exploracao_total": 0, "multiplicador_observado": 4.96})

    saida = _rodar_pintar_exploracao(dados)

    assert "com bônus (×5, estimado)" in saida
    assert "com bônus (×5, observado" not in saida


def test_card_a_bordo_volta_a_estimado_quando_observado_igual_ao_multiplicador():
    dados = _dados(vendido={"amostras": [], "quantidade": 0, "total": 0,
                            "exploracao_total": 0, "multiplicador_observado": 5.0})

    saida = _rodar_pintar_exploracao(dados)

    assert "com bônus (×5, estimado)" in saida
    assert "com bônus (×5, observado" not in saida


def test_repintar_mantem_os_nos_dos_cards_e_atualiza_o_texto():
    dados2 = _dados(vendido={"amostras": [], "quantidade": 9, "total": 9_000_000,
                             "exploracao_total": 0, "multiplicador_observado": None})

    saida = _rodar_js(
        "const antes = elements['exploracao-cartoes'].children.slice();"
        f"pintarExploracao({json.dumps(dados2)});"
        "const depois = elements['exploracao-cartoes'].children;"
        "console.log(antes.length === depois.length && antes.every((n, i) => n === depois[i]),"
        " textos(depois[1]).join('|'));", _dados())

    assert saida.startswith("true") and "9 amostras · 9,0 mi" in saida


def test_card_volta_a_ser_criado_depois_de_carregando():
    saida = _rodar_js(
        "const antes = elements['exploracao-cartoes'].children[0];"
        "pintarExploracao({carregando: true});"
        f"pintarExploracao({json.dumps(_dados())});"
        "console.log(elements['exploracao-cartoes'].children[0] !== antes,"
        " elements['exploracao-cartoes'].children.length);", _dados())

    assert saida.startswith("true 4")


def test_card_carreira_some_sem_statistics():
    assert "Carreira" not in _rodar_pintar_exploracao(_dados(carreira=None))


def test_modal_aberto_e_reescrito_no_polling():
    dados = _dados(vendido={"amostras": [_venda("Aleoida Arcus")], "quantidade": 1,
                            "total": 1, "exploracao_total": 0,
                            "multiplicador_observado": None})
    dados2 = _dados(vendido={"amostras": [_venda("Especie Da Segunda Leitura")],
                             "quantidade": 1, "total": 1, "exploracao_total": 0,
                             "multiplicador_observado": None})

    saida = _rodar_js("abrirModal('vendido'); elements['modal-corpo'].scrollTop = 120;"
                      f"pintarExploracao({json.dumps(dados2)});"
                      "console.log(elements['modal-exploracao'].open, elements['modal-corpo'].scrollTop,"
                      " textos(elements['modal-corpo']).join('|'));", dados)

    assert saida.startswith("true 120") and "Especie Da Segunda Leitura" in saida


def test_falha_nao_mexe_no_modal():
    dados = _dados(vendido={"amostras": [_venda("Aleoida Arcus")], "quantidade": 1,
                            "total": 1, "exploracao_total": 0,
                            "multiplicador_observado": None})

    saida = _rodar_js("abrirModal('vendido'); falhaExploracao();"
                      "console.log(elements['modal-exploracao'].open, textos(elements['modal-corpo']).join('|'));",
                      dados)

    assert saida.startswith("true") and "Aleoida Arcus" in saida


def test_fechar_modal_zera_a_chave_aberta():
    dados = _dados()

    saida = _rodar_js("abrirModal('vendido'); fecharModal();"
                      "console.log(elements['modal-exploracao'].open, modalAberto);", dados)

    assert saida.strip() == "false null"


def _rodar_atualizar(resposta_exploracao):
    """Roda o script inteiro com fetch falso: /estado.json falha, /exploracao.json
    devolve `resposta_exploracao` (ou falha, se for None)."""
    node_bin = shutil.which("node") or shutil.which("nodejs")
    if not node_bin:
        pytest.skip("node não encontrado")
    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
    stub = (NODE_STUB_EXPLORACAO +
            "function setInterval() {}\n"
            f"const RESPOSTA = {json.dumps(resposta_exploracao)};\n"
            "async function fetch(url) {\n"
            "  if (url === '/exploracao.json' && RESPOSTA !== null)\n"
            "    return { json: async () => RESPOSTA };\n"
            "  throw new Error('sem rede');\n"
            "}\n")
    programa = (stub + script +
                "setTimeout(() => {\n"
                "  console.log(textos(document.getElementById('exploracao-cartoes')).join('|'));\n"
                "  console.log('conexao=' + document.getElementById('conexao').textContent);\n"
                "}, 0);\n")
    r = subprocess.run([node_bin], input=programa, capture_output=True,
                       text=True, timeout=5)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_falha_ao_pintar_a_exploracao_aparece_na_aba():
    saida = _rodar_atualizar({"carregando": False})   # sem a_bordo: pintarExploracao quebra

    assert "não consegui ler a exploração" in saida
    assert "conexao=painel sem resposta" in saida


def test_falha_ao_buscar_a_exploracao_aparece_na_aba():
    saida = _rodar_atualizar(None)

    assert "não consegui ler a exploração" in saida


PRECOS = [{"especie": "Aleoida Gravis", "base": 12_934_900, "com_bonus": 64_674_500},
          {"especie": "Bacterium Acies", "base": 1_000_000, "com_bonus": 5_000_000}]


def _dados_precos():
    return _dados(precos=PRECOS, precos_atualizado_em="2026-11-14")


def test_tabela_de_precos_mostra_base_e_bonus():
    saida = _rodar_js("console.log(textos(elements['exploracao-precos']).join('|'));",
                      _dados_precos())
    assert "Aleoida Gravis" in saida and "12,9 mi" in saida and "64,7 mi" in saida
    assert "Com bônus (×5)" in saida and "2026-11-14" in saida


def test_busca_tem_aria_label():
    saida = _rodar_js("console.log(elements['busca-precos'].attrs['aria-label']);",
                      _dados_precos())
    assert saida.strip() == "buscar espécie"


def test_busca_ignora_acento_e_caixa():
    saida = _rodar_js("elements['busca-precos'].value = 'ACÍES'; filtrarPrecos();"
                      "console.log(JSON.stringify(linhasVisiveis()));", _dados_precos())
    assert json.loads(saida) == ["Bacterium Acies"]


def test_polling_nao_redesenha_a_tabela_nem_limpa_a_busca():
    dados = _dados_precos()
    saida = _rodar_js("elements['busca-precos'].value = 'acies'; filtrarPrecos();"
                      f"pintarExploracao({json.dumps(dados)});"
                      "console.log(elements['busca-precos'].value, JSON.stringify(linhasVisiveis()));",
                      dados)
    assert saida.startswith("acies") and "Aleoida" not in saida


def test_sem_precos_nao_desenha_tabela():
    saida = _rodar_js("console.log(textos(document.getElementById('exploracao-precos')).length);", _dados())
    assert saida.strip() == "0"


def test_rodape_sem_data_mostra_so_a_fonte():
    saida = _rodar_js("console.log(textos(elements['exploracao-precos']).join('|'));",
                      _dados(precos=PRECOS))
    assert "fonte: ed-dsn.net / Canonn" in saida and "atualizado" not in saida


def _dados_vendido(*valores):
    amostras = [_venda(f"Esp{i}", valor=v) for i, v in enumerate(valores)]
    return _dados(vendido={"amostras": amostras, "quantidade": len(amostras), "total": 0,
                           "exploracao_total": 0, "multiplicador_observado": None})


def _ordem_vendido(dados, extra):
    saida = _rodar_js("abrirModal('vendido');" + extra + """
const tabela = elements['modal-corpo'].children[0].children[1];
console.log(JSON.stringify({
  linhas: tabela.children[1].children.map(tr => tr.children.map(td => td.textContent)),
  cab: tabela.children[0].children[0].children.map(th => th.textContent)}));""", dados)
    return json.loads(saida)


def test_ordenar_coluna_numerica_usa_valor_cru():
    r = _ordem_vendido(_dados_vendido(5_000_000, 12_900_000, None), "ordenarPor('vendido', 2);")
    assert [l[2] for l in r["linhas"]] == ["12,9 mi", "5,0 mi", "—"]


def test_segundo_clique_inverte_e_vazio_continua_no_fim():
    r = _ordem_vendido(_dados_vendido(5_000_000, 12_900_000, None),
                       "ordenarPor('vendido', 2); ordenarPor('vendido', 2);")
    assert [l[2] for l in r["linhas"]] == ["5,0 mi", "12,9 mi", "—"]


def test_ordem_sobrevive_ao_polling():
    dados = _dados_vendido(5_000_000, 12_900_000, 8_000_000)
    r = _ordem_vendido(dados, f"ordenarPor('vendido', 2); pintarExploracao({json.dumps(dados)});")
    assert [l[2] for l in r["linhas"]] == ["12,9 mi", "8,0 mi", "5,0 mi"]


def test_ordenar_texto_ignora_acento_e_caixa():
    dados = _dados(vendido=_dados_vendido()["vendido"] | {"amostras": [
        _venda("zebra"), _venda("Éden"), _venda("abelha")], "quantidade": 3})
    r = _ordem_vendido(dados, "ordenarPor('vendido', 0);")
    assert [l[0] for l in r["linhas"]] == ["abelha", "Éden", "zebra"]


def test_seta_indica_coluna_e_sentido():
    r = _ordem_vendido(_dados_vendido(1, 2), "ordenarPor('vendido', 2);")
    assert "▼" in r["cab"][2] and "▲" not in "".join(r["cab"])
    r = _ordem_vendido(_dados_vendido(1, 2), "ordenarPor('vendido', 2); ordenarPor('vendido', 2);")
    assert "▲" in r["cab"][2]


def test_precos_ordenar_mantem_filtro():
    precos = PRECOS + [{"especie": "Bacterium Aurasus", "base": 800_000, "com_bonus": 4_000_000},
                       {"especie": "Bacterium Acies B", "base": 3_000_000, "com_bonus": 9_000_000}]
    saida = _rodar_js("elements['busca-precos'].value = 'acies'; filtrarPrecos();"
                      "ordenarPor('precos', 1);"
                      "console.log(JSON.stringify(linhasVisiveis()));",
                      _dados(precos=precos))
    assert json.loads(saida) == ["Bacterium Acies B", "Bacterium Acies"]


def test_precos_ordenar_nao_recria_a_busca():
    saida = _rodar_js("const b = elements['busca-precos']; ordenarPor('precos', 1);"
                      "console.log(elements['busca-precos'] === b);", _dados_precos())
    assert saida.strip() == "true"


def test_foco_no_cabecalho_do_modal_sobrevive_ao_polling():
    dados = _dados_vendido(5_000_000, 12_900_000)
    saida = _rodar_js("abrirModal('vendido');"
                      "const th = () => elements['modal-corpo'].children[0].children[1].children[0].children[0].children[2];"
                      "th().focus(); const antigo = th();"
                      f"pintarExploracao({json.dumps(dados)});"
                      "console.log(th() !== antigo, document.activeElement === th());", dados)
    assert saida.strip() == "true true"


def test_poll_sem_foco_no_modal_nao_foca_cabecalho():
    dados = _dados_vendido(5_000_000, 12_900_000)
    saida = _rodar_js("abrirModal('vendido');"
                      f"pintarExploracao({json.dumps(dados)});"
                      "const t = elements['modal-corpo'].children[0].children[1];"
                      "console.log(t.children[0].children[0].children.some(th => th.focado));", dados)
    assert saida.strip() == "false"


def _sessoes():
    return [{"sessao": "1", "quando": "2026-11-12T23:30:00Z", "vendido": 4_000_000, "a_bordo": 1_000_000},
            {"sessao": "2", "quando": "2026-11-13T11:00:00Z", "vendido": 0, "a_bordo": 2_000_000},
            {"sessao": "3", "quando": "2026-11-14T11:00:00Z", "vendido": 9_000_000, "a_bordo": 3_000_000}]


def test_card_sessoes_aparece_com_dados_e_some_sem():
    com = _rodar_pintar_exploracao(_dados(sessoes=_sessoes()))
    assert "Sessões" in com and "3 sessões" in com and "melhor: 12,0 mi" in com
    sem = _rodar_pintar_exploracao(_dados(sessoes=[]))
    assert "Sessões" not in sem
    ausente = _dados()
    del ausente["sessoes"]
    assert "Sessões" not in _rodar_pintar_exploracao(ausente)


def test_grafico_uma_barra_por_sessao_com_tooltip():
    saida = _rodar_js("""
const svg = graficoSessoes(%s);
const barras = svg.children.filter(g => g.attrs["class"] === "barra");
console.log(barras.length);
console.log(textos(barras[2]).join('|'));
console.log(barras[2].children.filter(c => c.tag === "rect").map(c => c.attrs.fill).join('|'));
console.log(textos(svg).join('|'));
console.log(svg.attrs.width, svg.attrs.viewBox);
console.log(TITULO_MODAL.sessoes);
console.log(textos(conteudoModal('sessoes', %s)).join('|'));
""" % (json.dumps(_sessoes()), json.dumps(_dados(sessoes=_sessoes()))), _dados(sessoes=_sessoes()))
    linhas = saida.splitlines()
    assert linhas[0] == "3"
    assert "14/11/2026" in linhas[1] and "12,0 mi" not in linhas[1] and "9,0 mi" in linhas[1]
    assert linhas[2] == "#ff8c1a|rgba(255,140,26,.35)"
    assert "12/11" in linhas[3] and "14/11" in linhas[3]
    assert linhas[4].startswith("100%")
    assert linhas[5] == "Ganhos por sessão (coleta)"
    assert "vendido" in linhas[6] and "a bordo (estimado)" in linhas[6]


def test_grafico_tudo_zero_nao_quebra():
    saida = _rodar_js("""
const zeros = [{sessao: "1", quando: "2026-11-14T11:00:00Z", vendido: 0, a_bordo: 0}];
const svg = graficoSessoes(zeros);
const g = svg.children.find(c => c.attrs["class"] === "barra");
console.log(g.children.filter(c => c.tag === "rect").map(c => c.attrs.height).join('|'));
""")
    assert saida.strip() == "0|0"


# --- Ficha do gênero ---

GENEROS = {
    "Aleoida": {"wiki": "Aleoida", "distancia_m": 150, "fonte_distancia": "wiki",
                "descricao": "Planta de mundos frios."},
    "Bacterium": {"wiki": None, "distancia_m": 500, "fonte_distancia": "comunidade",
                  "descricao": "Colônias bacterianas."},
}


def _dados_ficha(**mudancas):
    base = {"generos": GENEROS,
            "precos": [{"especie": "Aleoida Gravis", "genero": "Aleoida", "base": 1, "com_bonus": 5},
                       {"especie": "Sem Genero", "genero": None, "base": 2, "com_bonus": 10}],
            "precos_atualizado_em": "2026-11-14"}
    base.update(mudancas)
    return _dados(**base)


# fetch falso: conta chamadas e guarda as URLs.
FETCH_OK = """
let chamadas = [];
globalThis.fetch = async (url, opt) => { chamadas.push(url);
  return { json: async () => ({ query: { pages: { "42": { thumbnail: { source: "https://img/x.png" } } } } }) }; };
"""
FETCH_FALHA = """
let chamadas = [];
globalThis.fetch = async (url, opt) => { chamadas.push(url); throw new Error("rede"); };
"""
ACHAR = """
function achar(el, f) {
  if (f(el)) return el;
  for (const c of el.children || []) { const r = achar(c, f); if (r) return r; }
  return null;
}
"""


def test_ficha_mostra_descricao_distancia_e_fonte():
    saida = _rodar_js(FETCH_OK + "abrirFicha('Aleoida');"
                      "console.log(elements['modal-exploracao'].open, elements['modal-titulo'].textContent,"
                      " textos(elements['modal-corpo']).join('|'));", _dados_ficha())
    assert saida.startswith("true Aleoida")
    assert "Planta de mundos frios." in saida
    assert "Distância mínima entre amostras: 150 m (fonte: wiki)" in saida
    saida = _rodar_js(FETCH_OK + "abrirFicha('Bacterium');"
                      "console.log(textos(elements['modal-corpo']).join('|'));", _dados_ficha())
    assert "500 m (comunidade — confira no Codex)" in saida


def test_ficha_carrega_foto_da_wiki():
    saida = _rodar_js(FETCH_OK + ACHAR + """(async () => {
      abrirFicha('Aleoida'); await carregarFoto('Aleoida', 'Aleoida');
      const img = achar(elements['modal-corpo'], e => e.tag === 'img');
      const a = achar(elements['modal-corpo'], e => e.tag === 'a');
      console.log(img.src, img.alt, img.loading, a.href, a.target, a.rel, chamadas[0]);
    })();""", _dados_ficha())
    partes = saida.split()
    assert partes[:3] == ["https://img/x.png", "Aleoida", "lazy"]
    assert partes[3] == "https://elite-dangerous.fandom.com/wiki/Aleoida"
    assert partes[4:6] == ["_blank", "noopener"]
    assert "titles=Aleoida" in partes[6] and "pithumbsize=400" in partes[6] and "origin=*" in partes[6]


def test_ficha_foto_falha_mostra_indisponivel_e_link():
    saida = _rodar_js(FETCH_FALHA + ACHAR + """(async () => {
      abrirFicha('Aleoida'); await carregarFoto('Aleoida', 'Aleoida');
      console.log(textos(elements['modal-corpo']).join('|'),
        !!achar(elements['modal-corpo'], e => e.tag === 'img'),
        !!achar(elements['modal-corpo'], e => e.tag === 'a'), fotosGenero['Aleoida'].estado);
    })();""", _dados_ficha())
    assert "foto indisponível" in saida and saida.strip().endswith("false true falha")


def test_ficha_sem_pagina_wiki_nao_chama_fetch_e_linka_busca():
    saida = _rodar_js(FETCH_OK + ACHAR + """(async () => {
      abrirFicha('Bacterium'); await carregarFoto('Bacterium', null);
      const a = achar(elements['modal-corpo'], e => e.tag === 'a');
      console.log(chamadas.length, a.href, textos(elements['modal-corpo']).join('|'));
    })();""", _dados_ficha())
    assert saida.startswith("0 https://elite-dangerous.fandom.com/wiki/Special:Search?query=Bacterium")
    assert "foto indisponível" in saida


def test_foto_chega_depois_de_fechar_nao_mexe_no_modal():
    saida = _rodar_js(FETCH_OK + """(async () => {
      abrirFicha('Aleoida'); const p = carregarFoto('Aleoida', 'Aleoida');
      fecharModal(); abrirModal('vendido');
      const antes = textos(elements['modal-corpo']).join('|');
      await p;
      console.log(antes === textos(elements['modal-corpo']).join('|'), fichaAberta, modalAberto);
    })();""", _dados_ficha())
    assert saida.strip() == "true null vendido"


def test_foto_de_outra_ficha_nao_sobrescreve_a_atual():
    saida = _rodar_js(FETCH_OK + ACHAR + """(async () => {
      abrirFicha('Aleoida'); const p = carregarFoto('Aleoida', 'Aleoida');
      abrirFicha('Bacterium'); await p;
      console.log(!!achar(elements['modal-corpo'], e => e.tag === 'img'), elements['modal-titulo'].textContent);
    })();""", _dados_ficha())
    assert saida.strip() == "false Bacterium"


def test_voltar_reabre_o_modal_de_origem():
    saida = _rodar_js(FETCH_OK + ACHAR + """
      abrirModal('vendido'); abrirFicha('Aleoida');
      const durante = [modalAberto, modalAntesDaFicha, fichaAberta];
      // o polling não reescreve a ficha
      pintarExploracao(%s);
      const intacto = elements['modal-titulo'].textContent;
      const v = achar(elements['modal-corpo'], e => e.tag === 'button' && /voltar/.test(e.textContent || ''));
      v.onclick();
      console.log(JSON.stringify(durante), intacto, modalAberto, fichaAberta, modalAntesDaFicha,
        elements['modal-titulo'].textContent, elements['modal-exploracao'].open);
    """ % json.dumps(_dados_ficha()), _dados_ficha())
    assert saida.strip() == '[null,"vendido","Aleoida"] Aleoida vendido null null Vendido true'


def test_ficha_aberta_da_tabela_de_precos_nao_tem_voltar():
    saida = _rodar_js(FETCH_OK + ACHAR + "abrirFicha('Aleoida');"
                      "console.log(!!achar(elements['modal-corpo'], e => e.tag === 'button'),"
                      " modalAntesDaFicha, elements['modal-exploracao'].open);", _dados_ficha())
    assert saida.strip() == "false null true"


def test_fechar_zera_a_ficha():
    saida = _rodar_js(FETCH_OK + "abrirModal('vendido'); abrirFicha('Aleoida'); fecharModal();"
                      "console.log(fichaAberta, modalAntesDaFicha, modalAberto);", _dados_ficha())
    assert saida.strip() == "null null null"


def test_especie_sem_genero_nao_vira_link():
    saida = _rodar_js(ACHAR + """
      const tr = elements['exploracao-precos'];
      const botoes = [];
      (function andar(el) { if (el.className === 'link-especie') botoes.push(el.textContent);
        (el.children || []).forEach(andar); })(tr);
      const sem = achar(tr, e => e.tag === 'td' && e._t === 'Sem Genero');
      console.log(JSON.stringify(botoes), !!sem);
    """, _dados_ficha())
    assert saida.strip() == '["Aleoida Gravis"] true'


def test_busca_de_precos_continua_funcionando_com_link():
    saida = _rodar_js("elements['busca-precos'].value = 'GRAV'; filtrarPrecos();"
                      "console.log(JSON.stringify(linhasVisiveis()));", _dados_ficha())
    assert json.loads(saida) == ["Aleoida Gravis"]


def test_ordenar_precos_com_link_usa_o_texto_do_botao():
    saida = _rodar_js("ordenarPor('precos', 0);"
                      "console.log(JSON.stringify(linhasVisiveis()));", _dados_ficha())
    assert json.loads(saida) == ["Aleoida Gravis", "Sem Genero"]


def test_botao_da_especie_abre_a_ficha_em_a_bordo_e_vendido():
    am = {"especie": "Aleoida Arcus", "genero": "Aleoida", "especie_id": "x", "variante": "v",
          "corpo": "A 1", "sistema": "A", "quando": "t", "preco_base": 1, "bonus": "provavel"}
    saida = _rodar_js(ACHAR + """
      abrirModal('a_bordo');
      const b = achar(elements['modal-corpo'], e => e.className === 'link-especie');
      b.onclick({ stopPropagation() {} });
      console.log(fichaAberta, modalAntesDaFicha);
    """, _dados_ficha(a_bordo={"amostras": [am], "total_base": 1, "total_com_bonus": 1,
                               "provaveis_quantidade": 0, "provaveis_base": 0,
                               "provaveis_com_bonus": 0, "sistemas_exploracao": 0,
                               "corpos_exploracao": 0},
                      vendido={"amostras": [_venda(genero="Aleoida")], "quantidade": 1,
                               "total": 1, "exploracao_total": 0, "multiplicador_observado": None}))
    assert saida.strip() == "Aleoida a_bordo"
    saida = _rodar_js(ACHAR + """
      abrirModal('vendido');
      console.log(!!achar(elements['modal-corpo'], e => e.className === 'link-especie'));
    """, _dados_ficha(vendido={"amostras": [_venda(genero="Aleoida")], "quantidade": 1,
                               "total": 1, "exploracao_total": 0, "multiplicador_observado": None}))
    assert saida.strip() == "true"


def test_foto_em_cache_nao_busca_de_novo():
    saida = _rodar_js(FETCH_OK + """(async () => {
      abrirFicha('Aleoida'); await carregarFoto('Aleoida', 'Aleoida');
      fecharModal(); abrirFicha('Aleoida'); await carregarFoto('Aleoida', 'Aleoida');
      console.log(chamadas.length, fotosGenero['Aleoida'].estado);
    })();""", _dados_ficha())
    assert saida.strip() == "1 ok"
