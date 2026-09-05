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


def instalacao_com_market(market_id=4251780355, nome="Obra A", fornecido=4):
    inst = ed_parser.instalacao_de_payload(
        nome, [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": fornecido}],
        market_id=market_id,
    )
    return inst


def test_guarda_e_recupera_por_market_id(banco):
    banco.salvar(instalacao_com_market(), message_id=9, reportado_por="Arthur")

    registro = banco.obter(4251780355)

    assert registro.message_id == 9
    assert registro.reportado_por == "Arthur"
    assert registro.instalacao.market_id == 4251780355


def test_ainda_recupera_por_nome(banco):
    banco.salvar(instalacao_com_market(nome="Obra A"), message_id=9)

    assert banco.obter("Obra A").message_id == 9


def test_salvar_de_novo_com_o_mesmo_market_id_mas_nome_diferente_substitui(banco):
    """Mesmo market_id, nomes diferentes (e.g. "Desconhecida" → "Planetary Construction Site: X")."""
    banco.salvar(instalacao_com_market(nome="Desconhecida", fornecido=4), message_id=1)
    banco.salvar(instalacao_com_market(nome="Obra Resolvida", fornecido=9), message_id=2)

    assert banco.obter(4251780355).message_id == 2, "obter(market_id) deve devolver a mais recente"
    assert len(banco.listar()) == 1, "não pode haver duas linhas com o mesmo market_id"


def test_salvar_de_novo_com_o_mesmo_market_id_e_nome_substitui(banco):
    """Mesmo market_id, mesmo nome — atualiza na mesma linha."""
    banco.salvar(instalacao_com_market(nome="Obra A", fornecido=4), message_id=1)
    banco.salvar(instalacao_com_market(nome="Obra A", fornecido=9), message_id=2)

    assert banco.obter(4251780355).message_id == 2
    assert banco.obter("Obra A").message_id == 2
    assert len(banco.listar()) == 1


def test_reportado_por_vazio_quando_nao_informado(banco):
    banco.salvar(instalacao_com_market(), message_id=1)

    assert banco.obter(4251780355).reportado_por == ""


def test_obter_por_market_id_cai_para_nome_quando_registro_veio_da_reconciliacao(banco):
    """Reconciliação (servidor.reconciliar_com_o_canal) semeia o banco com
    market_id=None, porque a mensagem do Discord não carrega o MarketID.
    obter(market_id) tem que achar esse registro pelo nome, senão a mensagem
    antiga nunca é localizada para apagar e fica órfã no canal."""
    reconciliada = ed_parser.instalacao_de_payload(
        "Planetary Construction Site: X",
        [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
        market_id=None,
    )
    banco.salvar(reconciliada, message_id=1001)

    registro = banco.obter(555, nome=reconciliada.nome)

    assert registro is not None, "deveria cair para a busca por nome"
    assert registro.message_id == 1001


def test_migra_banco_antigo_sem_as_colunas_novas(tmp_path):
    """Já existe banco em produção sem market_id nem reportado_por."""
    import sqlite3

    caminho = str(tmp_path / "antigo.db")
    conexao = sqlite3.connect(caminho)
    conexao.execute(
        "CREATE TABLE instalacoes (nome TEXT PRIMARY KEY, message_id INTEGER NOT NULL, "
        "materiais TEXT NOT NULL, ultima_atualizacao TEXT NOT NULL, "
        "finalizado INTEGER NOT NULL DEFAULT 0)"
    )
    conexao.execute(
        "INSERT INTO instalacoes VALUES (?, ?, ?, ?, 0)",
        ("Obra Antiga", 77, '[{"Name_Localised":"Aço","RequiredAmount":10,"ProvidedAmount":2}]',
         "2026-09-03T12:00:00+00:00"),
    )
    conexao.commit()
    conexao.close()

    banco = arm.Armazenamento(caminho)

    registro = banco.obter("Obra Antiga")
    assert registro.message_id == 77, "o dado antigo não pode ser perdido"
    assert registro.reportado_por == ""
    assert registro.instalacao.market_id is None


def test_meta_devolve_o_padrao_quando_a_chave_nao_existe(banco):
    assert banco.obter_meta("consolidado_message_id") is None
    assert banco.obter_meta("consolidado_message_id", "vazio") == "vazio"


def test_meta_guarda_e_devolve(banco):
    banco.definir_meta("consolidado_message_id", "12345")

    assert banco.obter_meta("consolidado_message_id") == "12345"


def test_meta_sobrescreve_a_chave_existente(banco):
    banco.definir_meta("consolidado_message_id", "12345")
    banco.definir_meta("consolidado_message_id", "67890")

    assert banco.obter_meta("consolidado_message_id") == "67890"


def test_meta_sobrevive_a_reabertura_do_banco(tmp_path):
    caminho = str(tmp_path / "estado.db")
    arm.Armazenamento(caminho).definir_meta("chave", "valor")

    assert arm.Armazenamento(caminho).obter_meta("chave") == "valor"
