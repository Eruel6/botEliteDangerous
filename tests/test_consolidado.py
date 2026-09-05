import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import consolidado
import ed_parser


def _material(nome, requerido, fornecido, interno=""):
    return ed_parser.Material(
        nome=nome, nome_interno=interno, requerido=requerido, fornecido=fornecido
    )


def _obra(nome, materiais, market_id=None):
    return ed_parser.Instalacao(market_id=market_id, nome=nome, materiais=materiais)


def test_soma_o_mesmo_material_em_obras_diferentes():
    obras = [
        _obra("A", [_material("Steel", 100, 40)]),
        _obra("B", [_material("Steel", 200, 50)]),
    ]

    retrato = consolidado.consolidar(obras)

    assert len(retrato.linhas) == 1
    assert retrato.linhas[0].material == "Steel"
    assert retrato.linhas[0].faltando == 60 + 150
    assert retrato.linhas[0].obras == 2


def test_entrega_a_mais_nao_vira_desconto_em_outra_obra():
    """faltando tem piso em zero por obra: sem isso, 'A' com -50 comeria o de 'B'."""
    obras = [
        _obra("A", [_material("Steel", 100, 150)]),
        _obra("B", [_material("Steel", 100, 40)]),
    ]

    retrato = consolidado.consolidar(obras)

    assert retrato.linhas[0].faltando == 60
    assert retrato.linhas[0].obras == 1, "a obra completa não conta"


def test_agrupa_pelo_nome_localizado_ignorando_o_interno():
    """As linhas vindas da reconciliação do canal têm nome_interno vazio."""
    obras = [
        _obra("A", [_material("Steel", 100, 0, interno="steel")]),
        _obra("B", [_material("Steel", 100, 0, interno="")]),
    ]

    retrato = consolidado.consolidar(obras)

    assert len(retrato.linhas) == 1
    assert retrato.linhas[0].faltando == 200


def test_obra_completa_nao_entra_no_retrato():
    obras = [
        _obra("Pronta", [_material("Steel", 100, 100)]),
        _obra("Aberta", [_material("Steel", 100, 10)]),
    ]

    retrato = consolidado.consolidar(obras)

    assert retrato.obras == frozenset({"Aberta"})


def test_ordena_decrescente_com_desempate_por_nome():
    obras = [
        _obra("A", [
            _material("Zinco", 100, 0),
            _material("Alumínio", 100, 0),
            _material("Steel", 500, 0),
        ])
    ]

    retrato = consolidado.consolidar(obras)

    assert [l.material for l in retrato.linhas] == ["Steel", "Alumínio", "Zinco"]


def test_retratos_iguais_comparam_iguais():
    """decidir_acao compara dois retratos com ==; isso precisa valer."""
    obras = [_obra("A", [_material("Steel", 100, 0)])]

    assert consolidado.consolidar(obras) == consolidado.consolidar(obras)
