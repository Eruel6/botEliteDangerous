import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ardent


class RespostaFalsa:
    def __init__(self, status_code, dados=None, texto=None):
        self.status_code = status_code
        self._dados = dados
        self.text = texto if texto is not None else json.dumps(dados)

    def json(self):
        if self._dados is None:
            raise ValueError("não é JSON")
        return self._dados


UMA_ESTACAO = {
    "commodityName": "aluminium",
    "marketId": 3713691904,
    "stationName": "Nagasaki Terminal",
    "stationType": "Coriolis",
    "systemName": "Wregoe QI-M b48-6",
    "distance": 98,
    "distanceToArrival": 2100.5,
    "maxLandingPadSize": 3,
    "stock": 10039,
    "buyPrice": 127,
    "updatedAt": "2026-09-01T08:41:42.000Z",
}


def test_converte_o_nome_interno_para_o_da_api():
    assert ardent.nome_para_api("$Aluminium_name;") == "aluminium"


def test_converte_nome_sem_sufixo():
    assert ardent.nome_para_api("steel") == "steel"


def test_nome_interno_vazio_nao_e_consultavel():
    """Obra vinda da reconciliação do canal não tem nome interno."""
    assert ardent.nome_para_api("") == ""


def test_consulta_devolve_estacoes(monkeypatch):
    monkeypatch.setattr(
        ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, [UMA_ESTACAO])
    )

    (estacao,) = ardent.consultar("Sol", "aluminium", volume_minimo=100)

    assert estacao.nome == "Nagasaki Terminal"
    assert estacao.sistema == "Wregoe QI-M b48-6"
    assert estacao.distancia_ly == 98
    assert estacao.estoque == 10039
    assert estacao.preco == 127
    assert estacao.carrier is False


def test_reconhece_fleet_carrier(monkeypatch):
    carrier = dict(UMA_ESTACAO, stationType="FleetCarrier")
    monkeypatch.setattr(ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, [carrier]))

    (estacao,) = ardent.consultar("Sol", "aluminium", volume_minimo=100)

    assert estacao.carrier is True


def test_a_consulta_manda_raio_e_volume_minimo(monkeypatch):
    capturado = {}

    def get_falso(url, params=None, timeout=None):
        capturado["url"] = url
        capturado["params"] = params
        return RespostaFalsa(200, [])

    monkeypatch.setattr(ardent.requests, "get", get_falso)

    ardent.consultar("Wregoe KP-E c25-11", "aluminium", volume_minimo=180, raio=50)

    assert "Wregoe%20KP-E%20c25-11" in capturado["url"] or "Wregoe KP-E c25-11" in capturado["url"]
    assert capturado["params"] == {"maxDistance": 50, "minVolume": 180}


def test_lista_vazia_e_resposta_nao_erro(monkeypatch):
    """Commodity desconhecida devolve 200 com []. Isso é 'nada por perto'."""
    monkeypatch.setattr(ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, []))

    assert ardent.consultar("Sol", "naoexiste", volume_minimo=100) == []


def test_sistema_desconhecido_devolve_none(monkeypatch):
    monkeypatch.setattr(
        ardent.requests,
        "get",
        lambda *a, **k: RespostaFalsa(404, {"error": "Not Found", "message": "System not found"}),
    )

    assert ardent.consultar("Nao Existe", "aluminium", volume_minimo=100) is None


def test_timeout_devolve_none(monkeypatch):
    def get_estourando(*a, **k):
        raise OSError("tempo esgotado")

    monkeypatch.setattr(ardent.requests, "get", get_estourando)

    assert ardent.consultar("Sol", "aluminium", volume_minimo=100) is None


def test_json_invalido_devolve_none(monkeypatch):
    monkeypatch.setattr(
        ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, None, texto="<html>")
    )

    assert ardent.consultar("Sol", "aluminium", volume_minimo=100) is None


def test_resposta_que_nao_e_lista_devolve_none(monkeypatch):
    monkeypatch.setattr(ardent.requests, "get", lambda *a, **k: RespostaFalsa(200, {"a": 1}))

    assert ardent.consultar("Sol", "aluminium", volume_minimo=100) is None
