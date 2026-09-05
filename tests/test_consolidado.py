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


import datetime

QUANDO = datetime.datetime(2026, 9, 5, 14, 32, tzinfo=datetime.timezone.utc)


def test_corta_o_prefixo_de_construcao_do_nome():
    assert consolidado.nome_curto(
        "Planetary Construction Site: Pedder's Forge"
    ) == "Pedder's Forge"


def test_nome_sem_prefixo_aparece_inteiro():
    assert consolidado.nome_curto("Victoria Wolf Steel") == "Victoria Wolf Steel"


def test_nome_que_ficaria_vazio_apos_o_corte_aparece_inteiro():
    assert consolidado.nome_curto("Construction Site:") == "Construction Site:"


def test_mensagem_lista_as_obras_em_ordem_alfabetica_e_sem_prefixo():
    retrato = consolidado.consolidar([
        _obra("Orbital Construction Site: Victoria Wolf Steel", [_material("Steel", 10, 0)]),
        _obra("Planetary Construction Site: Pedder's Forge", [_material("Steel", 10, 0)]),
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert "Pedder's Forge · Victoria Wolf Steel" in texto
    assert "Construction Site:" not in texto


def test_a_ordem_das_obras_nao_depende_da_iteracao_do_frozenset():
    retrato = consolidado.consolidar([
        _obra(f"Obra {letra}", [_material("Steel", 10, 0)]) for letra in "ZMAK"
    ])

    primeira = consolidado.formatar_consolidado(retrato, QUANDO)
    outra_ordem = consolidado.Retrato(
        linhas=retrato.linhas, obras=frozenset(reversed(sorted(retrato.obras)))
    )

    assert consolidado.formatar_consolidado(outra_ordem, QUANDO) == primeira


def test_muitas_obras_cortam_a_linha_de_nomes_e_somam_o_resto():
    retrato = consolidado.consolidar([
        _obra(f"Obra Com Nome Bem Comprido Numero {i:02d}", [_material("Steel", 10, 0)])
        for i in range(40)
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)
    linha_obras = texto.splitlines()[1]
    mostradas = linha_obras.split(" · +")[0].split(" · ")

    assert len(linha_obras) <= consolidado.LIMITE_LINHA_OBRAS + 20
    assert f"+{40 - len(mostradas)} outras" in linha_obras


def test_cabe_em_2000_caracteres_com_muitos_materiais():
    retrato = consolidado.consolidar([
        _obra("A", [_material(f"Material Numero {i:03d}", 1000 - i, 0) for i in range(300)])
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert len(texto) <= consolidado.LIMITE_MENSAGEM


def test_o_resumo_do_corte_bate_com_o_que_ficou_de_fora():
    retrato = consolidado.consolidar([
        _obra("A", [_material(f"Material Numero {i:03d}", 1000 - i, 0) for i in range(300)])
    ])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)
    mostrados = sum(1 for l in texto.splitlines() if l.startswith("Material Numero"))
    cortados = 300 - mostrados
    soma_cortada = sum(l.faltando for l in retrato.linhas[mostrados:])

    assert f"+{cortados} materiais menores ({soma_cortada} no total)" in texto


def test_sem_corte_nao_ha_linha_de_resumo():
    retrato = consolidado.consolidar([_obra("A", [_material("Steel", 100, 0)])])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert "materiais menores" not in texto


def test_o_cabecalho_nao_e_confundido_com_mensagem_de_obra():
    """Se casasse, a reconciliação trataria o consolidado como uma obra."""
    retrato = consolidado.consolidar([_obra("A", [_material("Steel", 100, 0)])])

    texto = consolidado.formatar_consolidado(retrato, QUANDO)

    assert ed_parser.nome_na_mensagem(texto) is None


AGORA = datetime.datetime(2026, 9, 5, 20, 0, tzinfo=datetime.timezone.utc)
HA_UMA_HORA = AGORA - datetime.timedelta(hours=1)
HA_DEZ_MINUTOS = AGORA - datetime.timedelta(minutes=10)
HA_UM_DIA = AGORA - datetime.timedelta(days=1)


def _retrato(*obras):
    return consolidado.consolidar(list(obras))


def test_nada_mudou_nao_faz_nada():
    r = _retrato(_obra("A", [_material("Steel", 100, 0)]))

    assert consolidado.decidir_acao(r, r, HA_UMA_HORA, AGORA) == "nada"


def test_obra_nova_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "repostar"


def test_obra_que_ficou_pronta_reposta():
    antes = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 100)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "repostar"


def test_material_que_zerou_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "repostar"


def test_passou_a_janela_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_UM_DIA, AGORA) == "repostar"


def test_progresso_comum_so_edita():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_UMA_HORA, AGORA) == "editar"


def test_sem_repost_anterior_reposta():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, None, AGORA) == "repostar"


def test_cooldown_vence_a_obra_nova():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"


def test_cooldown_vence_a_obra_pronta():
    antes = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 0)]),
    )
    depois = _retrato(
        _obra("A", [_material("Steel", 100, 0)]),
        _obra("B", [_material("Steel", 100, 100)]),
    )

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"


def test_cooldown_vence_o_material_zerado():
    antes = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 0), _material("Ouro", 10, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"


def test_cooldown_vence_a_janela():
    """Impossível na prática, mas fixa a precedência: o cooldown vem primeiro."""
    antes = _retrato(_obra("A", [_material("Steel", 100, 0)]))
    depois = _retrato(_obra("A", [_material("Steel", 100, 10)]))

    assert consolidado.decidir_acao(antes, depois, HA_DEZ_MINUTOS, AGORA) == "editar"
