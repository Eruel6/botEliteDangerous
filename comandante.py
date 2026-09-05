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


@dataclass(frozen=True)
class Entrega:
    quando: str          # timestamp do evento, como veio do Journal
    market_id: int
    material: str        # nome localizado
    quantidade: int


@dataclass
class RetratoComandante:
    carga: dict = field(default_factory=dict)
    alvo_market_id: int = None
    alvo_sistema: str = ""
    entregas: list = field(default_factory=list)


def extrair_entregas(caminho_log):
    """Uma Entrega por material de cada ColonisationContribution do log.

    O cliente reenvia a sessão inteira a cada ciclo de propósito: o servidor
    deduplica por chave natural, então nada se perde num restart do Render e o
    cliente não precisa guardar estado.
    """
    entregas = []
    for registro in ed_parser.registros(caminho_log):
        if not isinstance(registro, dict):
            continue
        if registro.get("event") != "ColonisationContribution":
            continue
        market_id = registro.get("MarketID")
        quando = registro.get("timestamp")
        if market_id is None or not quando:
            continue
        for contribuicao in registro.get("Contributions") or []:
            if not isinstance(contribuicao, dict):
                continue
            material = contribuicao.get("Name_Localised") or contribuicao.get("Name")
            quantidade = contribuicao.get("Amount") or 0
            if material and quantidade > 0:
                entregas.append(
                    Entrega(
                        quando=quando,
                        market_id=market_id,
                        material=material,
                        quantidade=quantidade,
                    )
                )
    return entregas


def alvo_atual(caminho_log):
    """(market_id, sistema) da última obra vista no log. (None, "") se não houver."""
    market_id = None
    sistema = ""
    corrente = ""
    for registro in ed_parser.registros(caminho_log):
        if not isinstance(registro, dict):
            continue
        if registro.get("StarSystem"):
            corrente = registro["StarSystem"]
        if registro.get("event") == "ColonisationConstructionDepot":
            market_id = registro.get("MarketID")
            sistema = corrente
    return market_id, sistema


def montar_retrato(caminho_log, pasta=None):
    market_id, sistema = alvo_atual(caminho_log)
    return RetratoComandante(
        carga=ler_cargo_json(pasta),
        alvo_market_id=market_id,
        alvo_sistema=sistema,
        entregas=extrair_entregas(caminho_log),
    )
