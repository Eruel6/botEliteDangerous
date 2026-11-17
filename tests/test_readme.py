"""A lista do zip no README tem que trazer tudo o que o cliente importa."""

import ast
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Arquivos que não são import mas o cliente lê em tempo de execução.
DADOS_DO_CLIENTE = {"painel.html", "precos_vista.json", "generos_exobio.json", "config.exemplo.txt", "iniciar.bat"}


def lista_do_zip():
    with open(os.path.join(RAIZ, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    paragrafo = re.search(r"Monte um zip com:(.*?)\n\n", readme, re.S).group(1)
    return set(re.findall(r"`([^`]+)`", paragrafo))


def imports_locais(modulo, vistos=None):
    """Módulos do projeto que `modulo` importa, direta ou indiretamente
    (inclusive imports dentro de funções)."""
    vistos = set() if vistos is None else vistos
    with open(os.path.join(RAIZ, modulo + ".py"), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes = [a.name for a in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module and not no.level:
            nomes = [no.module]
        else:
            continue
        for nome in nomes:
            raiz = nome.split(".")[0]
            if raiz not in vistos and os.path.exists(os.path.join(RAIZ, raiz + ".py")):
                vistos.add(raiz)
                imports_locais(raiz, vistos)
    return vistos


def test_zip_do_readme_traz_tudo_o_que_o_cliente_importa():
    precisa = {m + ".py" for m in imports_locais("cliente") | {"cliente"}} | DADOS_DO_CLIENTE
    faltando = precisa - lista_do_zip()
    assert not faltando, f"faltam no zip do README: {sorted(faltando)}"


def test_zip_do_readme_so_lista_arquivos_que_existem():
    for nome in lista_do_zip():
        assert os.path.exists(os.path.join(RAIZ, nome)), nome


def test_grafo_do_cliente_inclui_a_exploracao():
    """Garante que o teste acima enxerga o import feito dentro de função."""
    assert {"leitor_exploracao", "exploracao", "precos_vista"} <= imports_locais("cliente")
