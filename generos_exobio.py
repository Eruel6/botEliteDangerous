# generos_exobio.py
"""Fichas dos gêneros de exobiologia (generos_exobio.json) e o mapeamento espécie -> gênero."""

import json
import os

from precos_vista import normalizar

CAMINHO_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generos_exobio.json")


class Generos:
    def __init__(self, dados: dict):
        self.dados = dados
        # nomes normalizados, do mais longo ao mais curto
        self._chaves = sorted(((normalizar(n), n) for n in dados), key=lambda p: -len(p[0]))

    def genero_de(self, nome_especie: str) -> str | None:
        norm = normalizar(nome_especie or "")
        for chave_norm, nome in self._chaves:
            if norm == chave_norm or norm.startswith(chave_norm + " "):
                return nome
        return None


def carregar_generos(caminho: str = CAMINHO_PADRAO) -> Generos:
    with open(caminho, encoding="utf-8") as f:
        return Generos(json.load(f)["generos"])
