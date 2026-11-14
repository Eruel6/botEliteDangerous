# precos_vista.py
"""Tabela de preços da Vista Genomics (venda de dados biológicos)."""
import html as _html
import json
import os
import re
import unicodedata

CAMINHO_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precos_vista.json")

_TABELA = re.compile(r'<table[^>]*id="tablepress-171".*?</table>', re.S)
_LINHA = re.compile(
    r'<td class="column-1">(.*?)</td>\s*<td class="column-2">(.*?)</td>', re.S
)


def extrair_precos_do_html(html: str) -> dict[str, int]:
    """Nome da espécie no site -> créditos."""
    tabela = _TABELA.search(html)
    if not tabela:
        return {}
    precos = {}
    for nome, valor in _LINHA.findall(tabela.group(0)):
        digitos = re.sub(r"\D", "", _html.unescape(valor))
        nome = _html.unescape(nome).strip()
        if nome and digitos:
            precos[nome] = int(digitos)
    return precos


def normalizar(nome: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.lower().split())


class Precos:
    def __init__(self, especies: dict[str, int], apelidos: dict[str, str] | None = None):
        self._especies = {normalizar(n): v for n, v in especies.items()}
        self._apelidos = {normalizar(a): normalizar(n) for a, n in (apelidos or {}).items()}

    def preco(self, nome_localizado: str) -> int | None:
        chave = normalizar(nome_localizado)
        chave = self._apelidos.get(chave, chave)
        return self._especies.get(chave)


def carregar_precos(caminho: str = CAMINHO_PADRAO) -> Precos:
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    return Precos(dados["especies"], dados.get("apelidos"))
