"""Consulta o Ardent Insight: onde comprar uma commodity perto de um sistema.

API pública, sem chave e sem SLA. Roda no cliente, nunca no servidor: a pergunta
é "perto de mim", e o que está perto de um piloto não está perto do outro.
"""

import urllib.parse
from dataclasses import dataclass

import requests

BASE = "https://api.ardent-insight.com/v2"
RAIO_PADRAO_LY = 50
TIMEOUT_SEGUNDOS = 30


@dataclass(frozen=True)
class Estacao:
    nome: str
    sistema: str
    distancia_ly: float
    distancia_ls: float
    estoque: int
    preco: int
    pad: int
    carrier: bool
    atualizado_em: str


def nome_para_api(nome_interno):
    """"$Aluminium_name;" vira "aluminium".

    A API só entende inglês. O Name_Localised do Journal está no idioma do jogo
    — em português, no caso do Arthur — e por isso não serve. Obra vinda da
    reconciliação do canal tem nome_interno vazio e devolve "": não consultável.
    """
    limpo = (nome_interno or "").strip().strip("$")
    if limpo.endswith("_name;"):
        limpo = limpo[: -len("_name;")]
    return limpo.lower()


def _para_estacao(bruto):
    return Estacao(
        nome=bruto.get("stationName", "?"),
        sistema=bruto.get("systemName", "?"),
        distancia_ly=bruto.get("distance") or 0,
        distancia_ls=bruto.get("distanceToArrival") or 0,
        estoque=bruto.get("stock") or 0,
        preco=bruto.get("buyPrice") or 0,
        pad=bruto.get("maxLandingPadSize") or 0,
        carrier=bruto.get("stationType") == "FleetCarrier",
        atualizado_em=bruto.get("updatedAt", ""),
    )


def consultar(sistema, material, volume_minimo, raio=RAIO_PADRAO_LY):
    """Estações que vendem ``material`` perto de ``sistema``.

    Devolve None quando não deu para saber (rede, timeout, 404, resposta
    estranha) e [] quando a API respondeu que não há nada. O painel trata os
    dois de forma diferente: um mantém o resultado anterior, o outro diz que
    não há nada por perto.
    """
    url = (
        f"{BASE}/system/name/{urllib.parse.quote(sistema)}"
        f"/commodity/name/{urllib.parse.quote(material)}/nearby/exports"
    )
    try:
        resposta = requests.get(
            url,
            params={"maxDistance": raio, "minVolume": volume_minimo},
            timeout=TIMEOUT_SEGUNDOS,
        )
        if resposta.status_code != 200:
            return None
        dados = resposta.json()
    except Exception:
        return None

    if not isinstance(dados, list):
        return None
    return [_para_estacao(b) for b in dados if isinstance(b, dict)]
