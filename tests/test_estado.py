import datetime
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ed_parser
import estado


def instalacao(nome="Planetary Construction Site: X", fornecido=4):
    return ed_parser.instalacao_de_payload(
        nome, [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": fornecido}]
    )


def test_comeca_sem_leitura_nem_envio():
    d = estado.EstadoCliente().como_dicionario()

    assert d["journal_atual"] is None
    assert d["ultimo_envio_ok"] is None
    assert d["instalacoes"] == []
    assert d["erros"] == []


def test_registra_a_leitura_com_as_instalacoes():
    e = estado.EstadoCliente()

    e.registrar_leitura("C:/Journal.01.log", [instalacao(fornecido=4)])
    d = e.como_dicionario()

    assert d["journal_atual"] == "C:/Journal.01.log"
    assert d["ultima_leitura"] is not None
    assert d["instalacoes"] == [
        {
            "nome": "Planetary Construction Site: X",
            "porcentagem": 40.0,
            "materiais_faltando": 1,
            "total_faltando": 6,
        }
    ]


def test_registra_envio_bem_sucedido():
    e = estado.EstadoCliente()

    e.registrar_envio(200)
    d = e.como_dicionario()

    assert d["ultimo_status_http"] == 200
    assert d["ultimo_envio_ok"] is not None


def test_envio_com_erro_nao_conta_como_envio_ok():
    e = estado.EstadoCliente()

    e.registrar_envio(401)
    d = e.como_dicionario()

    assert d["ultimo_status_http"] == 401
    assert d["ultimo_envio_ok"] is None


def test_guarda_os_erros_mais_recentes_primeiro():
    e = estado.EstadoCliente()

    e.registrar_erro("primeiro")
    e.registrar_erro("segundo")

    assert [x["mensagem"] for x in e.como_dicionario()["erros"]] == ["segundo", "primeiro"]


def test_descarta_erros_antigos_alem_do_limite():
    e = estado.EstadoCliente(max_erros=3)

    for i in range(5):
        e.registrar_erro(f"erro {i}")

    assert len(e.como_dicionario()["erros"]) == 3


def test_o_dicionario_e_serializavel_em_json():
    e = estado.EstadoCliente()
    e.registrar_leitura("C:/Journal.01.log", [instalacao()])
    e.registrar_envio(200)
    e.registrar_erro("algo quebrou")

    json.dumps(e.como_dicionario())
