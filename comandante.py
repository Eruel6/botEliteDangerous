"""O retrato do comandante: o que está no porão, o que ele entregou e para onde vai.

Roda no cliente. O Journal responde "o que foi entregue" e "qual a última obra
vista"; o porão detalhado só existe no Cargo.json, que o jogo sobrescreve.
"""

import json
import os
from dataclasses import dataclass, field

import ed_parser

NOME_ARQUIVO_CARGO = "Cargo.json"


def ler_cargo_json(pasta=None):
    """O porão como {material: quantidade}. Dicionário vazio em qualquer falha.

    O jogo reescreve o arquivo enquanto o cliente lê, então uma leitura no meio
    da escrita é esperada e não pode derrubar o ciclo.
    """
    base = os.path.expanduser(pasta or ed_parser.PASTA_JOURNAL_PADRAO)
    caminho = os.path.join(base, NOME_ARQUIVO_CARGO)

    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}

    if not isinstance(dados, dict):
        return {}

    porao = {}
    for item in dados.get("Inventory") or []:
        if not isinstance(item, dict):
            continue
        nome = item.get("Name_Localised") or item.get("Name")
        quantidade = item.get("Count") or 0
        if nome and quantidade > 0:
            porao[nome] = porao.get(nome, 0) + quantidade
    return porao
