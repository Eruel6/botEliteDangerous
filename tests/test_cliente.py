import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import cliente
import ed_parser

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BASICO = os.path.join(FIXTURES, "journal_basico.log")


def instalacao(nome="A", fornecido=1):
    return ed_parser.instalacao_de_payload(
        nome, [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": fornecido}]
    )


def test_payload_tem_o_formato_que_o_servidor_espera():
    payload = cliente.payload_de(instalacao("Planetary Construction Site: X", 4))

    assert payload == {
        "instalacao": "Planetary Construction Site: X",
        "materiais": [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
    }


def test_envia_todas_as_instalacoes_do_log_nao_so_a_ultima():
    enviados = []
    cliente.sincronizar(BASICO, {}, enviar=lambda p: enviados.append(p["instalacao"]))

    assert sorted(enviados) == [
        "Planetary Construction Site: Montes Biological Enterprise",
        "Planetary Construction Site: Pedder's Forge",
    ]


def test_nao_reenvia_instalacao_que_nao_mudou():
    enviados = []
    memoria = {}
    cliente.sincronizar(BASICO, memoria, enviar=lambda p: enviados.append(p["instalacao"]))
    enviados.clear()

    cliente.sincronizar(BASICO, memoria, enviar=lambda p: enviados.append(p["instalacao"]))

    assert enviados == []


def test_reenvia_quando_a_quantidade_fornecida_muda():
    memoria = {}
    cliente.sincronizar(BASICO, memoria, enviar=lambda p: None)
    enviados = []

    # simula progresso: a memória guarda o estado anterior
    memoria["Planetary Construction Site: Pedder's Forge"] = "estado-antigo"
    cliente.sincronizar(BASICO, memoria, enviar=lambda p: enviados.append(p["instalacao"]))

    assert enviados == ["Planetary Construction Site: Pedder's Forge"]


def test_ignora_instalacao_desconhecida():
    enviados = []
    cliente.sincronizar(
        os.path.join(FIXTURES, "journal_sem_nome.log"),
        {},
        enviar=lambda p: enviados.append(p["instalacao"]),
    )

    assert enviados == []


def test_manda_o_token_no_cabecalho(monkeypatch):
    capturado = {}

    def post_falso(url, json=None, headers=None, timeout=None):
        capturado["headers"] = headers

        class R:
            status_code = 200
            text = "ok"

        return R()

    monkeypatch.setattr(cliente.requests, "post", post_falso)
    monkeypatch.setattr(cliente, "API_TOKEN", "segredo")

    cliente.enviar_para_api(cliente.payload_de(instalacao()))

    assert capturado["headers"]["X-API-Token"] == "segredo"
