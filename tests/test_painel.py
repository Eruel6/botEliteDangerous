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
    tag: tag, children: [], textContent: undefined, className: undefined, style: {},
    replaceChildren() { this.children = []; },
    appendChild(c) { this.children.push(c); },
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
"""


def _rodar_pintar_exploracao(dados):
    node_bin = shutil.which("node") or shutil.which("nodejs")
    if not node_bin:
        pytest.skip("node não encontrado")
    with open(os.path.join(RAIZ, "painel.html"), encoding="utf-8") as f:
        html = f.read()
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
    script = script.split("async function atualizar")[0]
    programa = (NODE_STUB_EXPLORACAO + script +
                f"pintarExploracao({json.dumps(dados)});\n"
                "console.log(textos(elements['exploracao']).join('|'));\n")
    r = subprocess.run([node_bin], input=programa, capture_output=True,
                       text=True, timeout=5)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_pintar_exploracao_renderiza_amostra_a_bordo_e_primeiros():
    amostra = {"especie": "Bacterium Acies", "especie_id": "x", "variante": "Água-marinha",
               "corpo": "Plio Eurl IX-Z b14-0 B 1", "sistema": "Plio Eurl IX-Z b14-0",
               "quando": "2026-11-14T10:00:00Z", "preco_base": 5_000_000,
               "bonus": "provavel", "valor_estimado": 20_000_000, "sessao": 1}
    dados = {
        "carregando": False,
        "a_bordo": {"amostras": [amostra], "total_base": 5_000_000,
                    "total_com_bonus": 20_000_000, "sistemas_exploracao": 1,
                    "corpos_exploracao": 3},
        "vendido": {"amostras": [], "total": 0, "exploracao_total": 0},
        "perdido": {"amostras": 0, "sistemas": 0},
        "medias": {"por_amostra": 5_000_000, "por_planeta": None, "por_sessao": None},
        "primeiros": {"sistemas_descobertos": 0, "corpos_descobertos": 1,
                      "mapeados": 1, "pisados": 1,
                      "corpos": [{"corpo": "Plio Eurl IX-Z b14-0 B 1",
                                  "sistema": "Plio Eurl IX-Z b14-0",
                                  "descobriu": True, "mapeou": True, "pisou": True}]},
        "carreira": None,
    }

    saida = _rodar_pintar_exploracao(dados)

    assert "Bacterium Acies" in saida
    assert "provável" in saida
    assert "5,0 mi" in saida
    assert "Plio Eurl IX-Z b14-0 B 1" in saida


def test_pintar_exploracao_mostra_previsao_da_venda_e_a_carreira():
    dados = {
        "carregando": False,
        "a_bordo": {"amostras": [], "total_base": 0, "total_com_bonus": 0,
                    "sistemas_exploracao": 0, "corpos_exploracao": 0},
        "vendido": {"amostras": [
            {"especie": "Aleoida Arcus", "variante": "v", "corpo": "A 1", "sistema": "A",
             "quando": "2026-11-14T10:00:00Z", "valor": 7_000_000, "bonus_pago": False,
             "previsao": "provavel", "acertou": False, "sessao": 1}],
            "total": 7_000_000, "exploracao_total": 0},
        "perdido": {"amostras": 0, "sistemas": 0},
        "medias": {"por_amostra": None, "por_planeta": None, "por_sessao": None},
        "primeiros": {"sistemas_descobertos": 0, "corpos_descobertos": 0,
                      "mapeados": 0, "pisados": 0, "corpos": []},
        "carreira": {"Organic_Data": 27, "Organic_Data_Profits": 439_500_000,
                     "First_Logged": 25},
    }

    saida = _rodar_pintar_exploracao(dados)

    assert "Aleoida Arcus" in saida
    assert "previsão errada" in saida
    assert "439,5 mi" in saida


def test_pintar_exploracao_mostra_carregando():
    saida = _rodar_pintar_exploracao({"carregando": True})

    assert "lendo os journals" in saida
