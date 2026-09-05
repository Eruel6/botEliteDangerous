"""Consulta o Ardent Insight: onde comprar uma commodity perto de um sistema.

API pública, sem chave e sem SLA. Roda no cliente, nunca no servidor: a pergunta
é "perto de mim", e o que está perto de um piloto não está perto do outro.
"""

import datetime
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


VALIDADE_DIAS = 30
MAXIMO_POR_MATERIAL = 3

#: Pad exigido por nave: 1 pequeno, 2 médio, 3 grande.
#:
#: A tabela lista **apenas** naves que exigem pad GRANDE. Nave pequena ou
#: média pousa em qualquer lugar, por isso nenhuma delas está aqui. Uma nave
#: ausente cai no padrão 1, que não filtra nada.
#:
#: Filtrar errado — listar uma nave de pad médio como se fosse grande —
#: esconderia estação boa. Não filtrar — deixar uma nave desconhecida de fora
#: — só deixa passar estação ruim. Por isso, adicione uma nave só se tiver
#: verificado que ela exige pad grande.
#:
#: type9 está confirmado pelo Loadout real do Arthur. Os demais foram
#: verificados na wiki do Elite Dangerous e em INARA.
PAD_POR_NAVE = {
    "type9": 3,
    "type9_military": 3,
    "type7": 3,
    "anaconda": 3,
    "cutter": 3,
    "federation_corvette": 3,
    "belugaliner": 3,
}


def pad_necessario(nave):
    return PAD_POR_NAVE.get((nave or "").lower(), 1)


def _idade_em_dias(atualizado_em, agora):
    """None quando a data não é legível — nesse caso a estação é descartada."""
    try:
        quando = datetime.datetime.fromisoformat(
            (atualizado_em or "").replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=datetime.timezone.utc)
    return (agora - quando).total_seconds() / 86400


def melhores(estacoes, pad_minimo, agora, quantas=MAXIMO_POR_MATERIAL):
    """As melhores estações depois dos filtros de pad e validade.

    Estoque e raio já foram filtrados pela própria API, via minVolume e
    maxDistance — melhor cortar lá do que baixar e descartar aqui.
    """
    servem = []
    for estacao in estacoes:
        if estacao.pad < pad_minimo:
            continue
        idade = _idade_em_dias(estacao.atualizado_em, agora)
        if idade is None or idade > VALIDADE_DIAS:
            continue
        servem.append(estacao)

    servem.sort(key=lambda e: (e.distancia_ly, e.preco, e.nome))
    return servem[:quantas]
