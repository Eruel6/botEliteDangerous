"""Lê e valida o config.txt que fica ao lado do iniciar.bat."""

import os
from dataclasses import dataclass


class ConfigInvalida(Exception):
    """Config ausente ou incompleta. A mensagem diz o que fazer."""


@dataclass
class Config:
    api_token: str
    api_url: str


def _ler_pares(caminho):
    pares = {}
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            pares[chave.strip()] = valor.strip()
    return pares


def carregar_config(caminho="config.txt"):
    if not os.path.exists(caminho):
        raise ConfigInvalida(
            f"Não encontrei {caminho}. Copie config.exemplo.txt para config.txt "
            "e coloque nele o token que você recebeu."
        )

    pares = _ler_pares(caminho)
    faltando = [c for c in ("API_TOKEN", "API_URL") if not pares.get(c)]
    if faltando:
        raise ConfigInvalida(
            f"Faltou preencher em {caminho}: {', '.join(faltando)}."
        )

    return Config(api_token=pares["API_TOKEN"], api_url=pares["API_URL"])
