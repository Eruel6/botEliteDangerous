import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ed_parser as ed

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BASICO = os.path.join(FIXTURES, "journal_basico.log")


def test_extrai_uma_instalacao_por_market_id():
    instalacoes = ed.extrair_instalacoes(BASICO)
    assert [i.market_id for i in instalacoes] == [4251780355, 4251881219]


def test_resolve_nome_da_instalacao_pelo_market_id():
    a, b = ed.extrair_instalacoes(BASICO)
    assert a.nome == "Planetary Construction Site: Pedder's Forge"
    assert b.nome == "Planetary Construction Site: Montes Biological Enterprise"


def test_nome_e_desconhecida_quando_nao_ha_approach_settlement():
    (inst,) = ed.extrair_instalacoes(os.path.join(FIXTURES, "journal_sem_nome.log"))
    assert inst.nome == "Desconhecida"


def test_mantem_o_estado_mais_recente_de_cada_instalacao():
    a, _ = ed.extrair_instalacoes(BASICO)
    assert a.progresso == 1.0
    assert a.completa is True
    assert a.falhou is False
    assert [m.fornecido for m in a.materiais] == [1677, 124, 165]


def test_material_expõe_nome_localizado_e_quantidade_faltante():
    _, b = ed.extrair_instalacoes(BASICO)
    aco = b.materiais[0]
    assert aco.nome == "Aço"
    assert aco.requerido == 900
    assert aco.fornecido == 90
    assert aco.faltando == 810


def test_porcentagem_usa_soma_de_quantidades():
    _, b = ed.extrair_instalacoes(BASICO)
    assert b.porcentagem == 90 / 1300 * 100


def test_log_sem_depot_nao_retorna_instalacoes():
    assert ed.extrair_instalacoes(os.path.join(FIXTURES, "journal_sem_depot.log")) == []


def test_encontra_o_journal_modificado_mais_recentemente(tmp_path):
    antigo = tmp_path / "Journal.2025-01-01T000000.01.log"
    recente = tmp_path / "Journal.2025-06-01T000000.01.log"
    antigo.write_text("{}\n")
    recente.write_text("{}\n")
    os.utime(antigo, (1, 1))
    os.utime(recente, (2, 2))

    assert ed.encontrar_log_mais_recente(str(tmp_path)) == str(recente)


def test_encontrar_log_devolve_none_quando_pasta_nao_tem_journal(tmp_path):
    (tmp_path / "outra-coisa.txt").write_text("nada")
    assert ed.encontrar_log_mais_recente(str(tmp_path)) is None


def test_mensagem_do_discord_inclui_porcentagem_quando_informada():
    a, _ = ed.extrair_instalacoes(BASICO)
    cabecalho = ed.formatar_mensagem_discord(a, porcentagem="100.0%").splitlines()[0]
    assert cabecalho.endswith("`Planetary Construction Site: Pedder's Forge` `100.0%`")


def test_mensagem_do_discord_e_uma_string_bem_formada():
    """Invariante do formatador: a saída codifica em UTF-8 sem surrogates soltos.

    Não é regressão de bug conhecido: o discord.py serializa em JSON, e o
    json.dumps escapa surrogates soltos como \\uXXXX, então eles chegariam
    corretos ao Discord de qualquer forma. É só uma garantia barata de que a
    string vale para qualquer outro consumidor (log, arquivo, terminal).
    """
    a, _ = ed.extrair_instalacoes(BASICO)
    ed.formatar_mensagem_discord(a).encode("utf-8")


def test_instalacao_a_partir_do_payload_da_api():
    inst = ed.instalacao_de_payload(
        "Planetary Construction Site: X",
        [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
    )
    assert inst.nome == "Planetary Construction Site: X"
    assert inst.materiais[0].faltando == 6
    assert inst.porcentagem == 40.0


def test_ultima_instalacao_e_a_atualizada_por_ultimo_no_log():
    # No fixture, o último ColonisationConstructionDepot é o da instalação A.
    assert ed.ultima_instalacao(BASICO).market_id == 4251780355


def test_ultima_instalacao_e_none_em_log_sem_depot():
    assert ed.ultima_instalacao(os.path.join(FIXTURES, "journal_sem_depot.log")) is None


def test_sinais_de_construcao_lista_os_sites_anunciados_no_log():
    assert ed.sinais_de_construcao(BASICO) == {
        "Planetary Construction Site: Pedder's Forge",
        "Planetary Construction Site: Montes Biological Enterprise",
    }


def test_sinais_de_construcao_ignora_sinais_de_outros_tipos():
    assert ed.sinais_de_construcao(os.path.join(FIXTURES, "journal_sem_depot.log")) == set()


def test_le_de_volta_o_nome_da_instalacao_a_partir_da_mensagem_postada():
    a, _ = ed.extrair_instalacoes(BASICO)
    conteudo = ed.formatar_mensagem_discord(a, porcentagem="97.5%")

    assert ed.nome_na_mensagem(conteudo) == "Planetary Construction Site: Pedder's Forge"


def test_le_de_volta_o_nome_em_mensagem_sem_porcentagem():
    a, _ = ed.extrair_instalacoes(BASICO)

    assert ed.nome_na_mensagem(ed.formatar_mensagem_discord(a)) == a.nome


def test_nome_na_mensagem_devolve_none_para_texto_alheio():
    assert ed.nome_na_mensagem("oi pessoal, alguem vai pra Colonia hoje?") is None


def test_le_de_volta_os_materiais_a_partir_da_mensagem_postada():
    a, _ = ed.extrair_instalacoes(BASICO)
    conteudo = ed.formatar_mensagem_discord(a, porcentagem="100.0%")

    lidos = ed.materiais_na_mensagem(conteudo)

    assert [(m.nome, m.requerido, m.fornecido) for m in lidos] == [
        (m.nome, m.requerido, m.fornecido) for m in a.materiais
    ]


def test_le_de_volta_materiais_com_nome_maior_que_a_coluna():
    inst = ed.instalacao_de_payload(
        "X",
        [{"Name_Localised": "Fabricantes de construções pesadas", "RequiredAmount": 165, "ProvidedAmount": 3}],
    )
    (lido,) = ed.materiais_na_mensagem(ed.formatar_mensagem_discord(inst))

    assert (lido.nome, lido.requerido, lido.fornecido) == ("Fabricantes de construções pesadas", 165, 3)


def test_materiais_na_mensagem_devolve_vazio_para_texto_alheio():
    assert ed.materiais_na_mensagem("papo do canal") == []


# --- resolução de nome: instalações que sumiam das mensagens -------------------


def test_resolve_nome_quando_approach_settlement_traz_o_nome_cru():
    """O jogo às vezes reporta 'Sweet Beacon' em vez de 'Planetary Construction
    Site: Sweet Beacon'. Antes isso virava Desconhecida e a instalação sumia."""
    (inst,) = ed.extrair_instalacoes(os.path.join(FIXTURES, "journal_nome_cru.log"))

    assert inst.nome == "Planetary Construction Site: Sweet Beacon"


def test_resolve_nome_de_instalacao_conhecida_apenas_por_docked():
    """Sites orbitais não geram ApproachSettlement — só Docked."""
    (inst,) = ed.extrair_instalacoes(os.path.join(FIXTURES, "journal_so_docked.log"))

    assert inst.nome == "Orbital Construction Site: Vulcan Gate"


def test_continua_desconhecida_quando_nao_ha_nenhuma_fonte_de_nome():
    (inst,) = ed.extrair_instalacoes(os.path.join(FIXTURES, "journal_sem_fonte_de_nome.log"))

    assert inst.nome == ed.NOME_DESCONHECIDO


def test_sinais_de_construcao_inclui_sites_orbitais():
    assert ed.sinais_de_construcao(os.path.join(FIXTURES, "journal_nome_cru.log")) == {
        "Planetary Construction Site: Sweet Beacon"
    }


def test_instalacao_de_payload_aceita_market_id():
    inst = ed.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
        market_id=4251780355,
    )

    assert inst.market_id == 4251780355


def test_instalacao_de_payload_sem_market_id_continua_none():
    inst = ed.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}]
    )

    assert inst.market_id is None


def test_rodape_vira_subtexto_na_ultima_linha():
    a, _ = ed.extrair_instalacoes(BASICO)

    msg = ed.formatar_mensagem_discord(a, porcentagem="40.0%", rodape="atualizado por Fulano às 14:32")

    assert msg.splitlines()[-1] == "-# atualizado por Fulano às 14:32"


def test_sem_rodape_a_mensagem_nao_ganha_linha_extra():
    a, _ = ed.extrair_instalacoes(BASICO)

    assert ed.formatar_mensagem_discord(a).splitlines()[-1] == "```"


def test_rodape_nao_atrapalha_a_releitura_da_mensagem():
    """A reconciliação relê as próprias mensagens; o rodapé não pode virar material."""
    a, _ = ed.extrair_instalacoes(BASICO)
    msg = ed.formatar_mensagem_discord(a, porcentagem="40.0%", rodape="atualizado por Fulano às 14:32")

    assert ed.nome_na_mensagem(msg) == a.nome
    assert len(ed.materiais_na_mensagem(msg)) == len(a.materiais)


COM_SISTEMA = os.path.join(FIXTURES, "journal_com_sistema.log")


def test_registros_e_publico_e_devolve_os_eventos():
    eventos = [r.get("event") for r in ed.registros(COM_SISTEMA)]

    assert eventos == [
        "FSDJump",
        "ApproachSettlement",
        "ColonisationConstructionDepot",
        "FSDJump",
    ]


def test_a_obra_recebe_o_sistema_corrente():
    """ApproachSettlement não traz StarSystem; o sistema vem do FSDJump anterior."""
    (obra,) = ed.extrair_instalacoes(COM_SISTEMA)

    assert obra.sistema == "Wregoe KP-E c25-11"


def test_o_sistema_e_o_do_momento_da_obra_nao_o_ultimo_do_log():
    """O log termina em outro sistema; a obra continua no sistema onde foi vista."""
    (obra,) = ed.extrair_instalacoes(COM_SISTEMA)

    assert obra.sistema != "Outro Sistema"


def test_instalacao_de_payload_aceita_sistema():
    inst = ed.instalacao_de_payload("X", [], market_id=1, sistema="Sol")

    assert inst.sistema == "Sol"


def test_instalacao_de_payload_sem_sistema_fica_vazia():
    inst = ed.instalacao_de_payload("X", [], market_id=1)

    assert inst.sistema == ""


def test_sistema_atual_e_o_ultimo_starsystem_do_log():
    assert ed.sistema_atual(COM_SISTEMA) == "Outro Sistema"


def test_sistema_atual_segue_o_piloto_e_nao_a_obra():
    """O piloto saiu do sistema da obra; sistema_atual segue o piloto, alvo_atual não."""
    import comandante

    _, sistema_da_obra = comandante.alvo_atual(COM_SISTEMA)

    assert sistema_da_obra == "Wregoe KP-E c25-11"
    assert ed.sistema_atual(COM_SISTEMA) == "Outro Sistema"


def test_sistema_atual_vazio_sem_starsystem_no_log():
    assert ed.sistema_atual(os.path.join(FIXTURES, "journal_sem_depot.log")) == ""


def test_credito_ordena_do_maior_para_o_menor():
    assert ed.formatar_creditos({"btpopov": 720, "Eruel": 1440}) == (
        "entregue: Eruel 1440t · btpopov 720t"
    )


def test_sem_entrega_nao_ha_linha_de_credito():
    assert ed.formatar_creditos({}) == ""


def test_credito_corta_no_limite_e_resume():
    muitos = {f"Piloto{i:02d}": 100 - i for i in range(40)}

    linha = ed.formatar_creditos(muitos, limite=120)

    assert len(linha) <= 140
    assert "+" in linha.rsplit("·", 1)[-1]


def test_a_mensagem_de_obra_carrega_o_credito():
    inst = ed.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}]
    )

    texto = ed.formatar_mensagem_discord(
        inst, "40.0%", rodape="atualizado por Eruel", creditos={"Eruel": 1440}
    )

    assert "-# entregue: Eruel 1440t" in texto


def test_o_credito_e_relido_da_mensagem():
    inst = ed.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}]
    )
    texto = ed.formatar_mensagem_discord(
        inst, "40.0%", creditos={"Eruel": 1440, "btpopov": 720}
    )

    assert ed.creditos_na_mensagem(texto) == {"Eruel": 1440, "btpopov": 720}


def test_mensagem_sem_credito_relida_devolve_vazio():
    inst = ed.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}]
    )

    assert ed.creditos_na_mensagem(ed.formatar_mensagem_discord(inst)) == {}


COM_LOADOUT = os.path.join(FIXTURES, "journal_com_loadout.log")


def test_a_nave_e_a_capacidade_vem_do_loadout():
    assert ed.nave_atual(COM_LOADOUT) == ("type9", 720)


def test_log_sem_loadout_devolve_nave_vazia():
    assert ed.nave_atual(os.path.join(FIXTURES, "journal_sem_depot.log")) == ("", 0)
