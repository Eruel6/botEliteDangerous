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
    tag: tag, children: [], textContent: undefined, className: undefined, style: {},
    scrollTop: 0, open: false,
    replaceChildren(...novos) { this.children = novos; },
    appendChild(c) { this.children.push(c); },
    showModal() { this.open = true; },
    close() { this.open = false; },
    addEventListener() {},
    setAttribute() {},
  };
}
const document = {
  getElementById(id) { return elements[id] || (elements[id] = novo(id)); },
  createElement: novo,
};
function textos(el) {
  let r = [];
  if (el.textContent) r.push(el.textContent);
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


def _rodar_js(programa_extra, dados=None):
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
                       text=True, timeout=5)
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
