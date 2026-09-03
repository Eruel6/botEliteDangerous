import datetime
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import armazenamento as arm
import ed_parser


@pytest.fixture
def banco(tmp_path):
    return arm.Armazenamento(str(tmp_path / "estado.db"))


def instalacao(nome="Planetary Construction Site: X", fornecido=4):
    return ed_parser.instalacao_de_payload(
        nome, [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": fornecido}]
    )


def test_guarda_e_recupera_o_id_da_mensagem(banco):
    inst = instalacao()
    banco.salvar(inst, message_id=999)

    registro = banco.obter(inst.nome)
    assert registro.message_id == 999
    assert registro.finalizado is False


def test_recupera_os_materiais_como_objetos_do_parser(banco):
    inst = instalacao(fornecido=4)
    banco.salvar(inst, message_id=1)

    material = banco.obter(inst.nome).instalacao.materiais[0]
    assert material.nome == "Aço"
    assert material.faltando == 6


def test_salvar_de_novo_substitui_o_registro_anterior(banco):
    inst = instalacao()
    banco.salvar(inst, message_id=1)
    banco.salvar(instalacao(fornecido=10), message_id=2)

    assert banco.obter(inst.nome).message_id == 2
    assert len(banco.listar()) == 1


def test_estado_sobrevive_a_reabertura_do_banco(tmp_path):
    caminho = str(tmp_path / "estado.db")
    arm.Armazenamento(caminho).salvar(instalacao(), message_id=7)

    assert arm.Armazenamento(caminho).obter(instalacao().nome).message_id == 7


def test_obter_devolve_none_para_instalacao_desconhecida(banco):
    assert banco.obter("nao existe") is None


def test_marcar_finalizado(banco):
    inst = instalacao()
    banco.salvar(inst, message_id=1)

    banco.marcar_finalizado(inst.nome)

    assert banco.obter(inst.nome).finalizado is True


def test_listar_traz_apenas_os_nao_finalizados_quando_pedido(banco):
    banco.salvar(instalacao("A"), message_id=1)
    banco.salvar(instalacao("B"), message_id=2)
    banco.marcar_finalizado("A")

    assert [r.instalacao.nome for r in banco.listar(pendentes=True)] == ["B"]


def test_guarda_o_momento_da_ultima_atualizacao(banco):
    antes = datetime.datetime.now(datetime.timezone.utc)
    banco.salvar(instalacao(), message_id=1)
    depois = datetime.datetime.now(datetime.timezone.utc)

    quando = banco.obter(instalacao().nome).ultima_atualizacao
    assert antes <= quando <= depois


def test_usa_CAMINHO_DB_definido_depois_do_import(monkeypatch, tmp_path):
    """A env é lida na construção, não no import — senão o caminho fica congelado."""
    destino = tmp_path / "definido-depois.db"
    monkeypatch.setenv("CAMINHO_DB", str(destino))

    arm.Armazenamento().salvar(instalacao(), message_id=1)

    assert destino.exists()
