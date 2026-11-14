# tests/test_exploracao.py
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import exploracao
import precos_vista

SESSAO = "Journal.teste.log"
SA = 111


def historico_da_fixture(nome):
    h = exploracao.Historico(precos_vista.carregar_precos())
    with open(os.path.join(RAIZ, "tests", "fixtures", nome), encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                h.consumir(json.loads(linha), nome)
    return h


def historico_vazio(especies=None):
    return exploracao.Historico(precos_vista.Precos(especies or {"Bacterium Acies": 1_000_000}))


def scan(body_id, nome=None, descoberto=False, mapeado=False, pisado=False,
         sistema="Sis", dist=10.0, sa=SA):
    return {"timestamp": "2026-11-14T10:00:00Z", "event": "Scan",
            "BodyName": nome or f"{sistema} {body_id}", "BodyID": body_id,
            "StarSystem": sistema, "SystemAddress": sa, "DistanceFromArrivalLS": dist,
            "WasDiscovered": descoberto, "WasMapped": mapeado, "WasFootfalled": pisado}


def organico(tipo, body=7, especie="Bacterium Acies", quando="2026-11-14T11:00:00Z", sa=SA):
    return {"timestamp": quando, "event": "ScanOrganic", "ScanType": tipo,
            "Species": "$Codex_Ent_Bacterial_04_Name;", "Species_Localised": especie,
            "Variant_Localised": f"{especie} - Verde", "SystemAddress": sa, "Body": body}


def test_journal_real_gera_uma_amostra_a_bordo_com_bonus_provavel():
    r = historico_da_fixture("journal_exobio.log").resumo()
    [a] = r["a_bordo"]["amostras"]
    assert a["especie"] == "Bacterium Acies"
    assert a["especie_id"] == "$Codex_Ent_Bacterial_04_Name;"
    assert a["corpo"] == "Plio Eurl IX-Z b14-0 B 1"
    assert a["sistema"] == "Plio Eurl IX-Z b14-0"
    assert a["quando"] == "2026-11-14T13:42:14Z"
    assert (a["preco_base"], a["bonus"], a["valor_estimado"]) == (1_000_000, "provavel", 5_000_000)
    assert r["a_bordo"]["total_base"] == 1_000_000
    assert r["a_bordo"]["total_com_bonus"] == 5_000_000


def test_log_e_sample_nao_geram_amostra():
    h = historico_vazio()
    for tipo in ("Log", "Sample", "Sample"):
        h.consumir(organico(tipo), SESSAO)
    assert h.resumo()["a_bordo"]["amostras"] == []


def test_journal_real_marca_b1_como_descoberto_mapeado_e_pisado():
    p = historico_da_fixture("journal_exobio.log").resumo()["primeiros"]
    b1 = next(c for c in p["corpos"] if c["corpo"] == "Plio Eurl IX-Z b14-0 B 1")
    assert (b1["descobriu"], b1["mapeou"], b1["pisou"]) == (True, True, True)
    assert p["sistemas_descobertos"] == 0
    assert p["corpos_descobertos"] == 19
    assert p["mapeados"] == 1
    assert p["pisados"] == 1


def test_scan_posterior_nao_apaga_primeira_descoberta():
    h = historico_vazio()
    h.consumir(scan(3, descoberto=False), SESSAO)
    h.consumir(scan(3, descoberto=True), SESSAO)
    [c] = h.resumo()["primeiros"]["corpos"]
    assert c["descobriu"] is True


def test_amostra_em_corpo_sem_scan_tem_bonus_desconhecido_e_nome_de_fallback():
    h = historico_vazio()
    h.consumir(organico("Analyse", body=7), SESSAO)
    [a] = h.resumo()["a_bordo"]["amostras"]
    assert a["corpo"] == "corpo 7"
    assert a["bonus"] == "desconhecido"
    assert a["valor_estimado"] == a["preco_base"] == 1_000_000


def test_amostra_em_corpo_ja_pisado_tem_bonus_improvavel():
    h = historico_vazio()
    h.consumir(scan(7, pisado=True), SESSAO)
    h.consumir(organico("Analyse", body=7), SESSAO)
    [a] = h.resumo()["a_bordo"]["amostras"]
    assert a["bonus"] == "improvavel"
    assert a["valor_estimado"] == 1_000_000


def test_especie_sem_preco_fica_sem_valor_e_fora_dos_totais():
    h = historico_vazio()
    h.consumir(organico("Analyse", especie="Especie Nova"), SESSAO)
    h.consumir(organico("Analyse"), SESSAO)
    r = h.resumo()["a_bordo"]
    sem = next(a for a in r["amostras"] if a["especie"] == "Especie Nova")
    assert sem["preco_base"] is None and sem["valor_estimado"] is None
    assert r["total_base"] == 1_000_000


def test_carreira_vem_do_ultimo_statistics():
    r = historico_da_fixture("journal_exobio.log").resumo()
    assert r["carreira"]["Organic_Data_Profits"] == 439_542_900


def test_sistema_descoberto_pela_estrela_de_chegada():
    h = historico_vazio()
    h.consumir(scan(0, descoberto=False, dist=0.0), SESSAO)
    h.consumir(scan(1, descoberto=True, dist=0.0, sistema="Outro", sa=222), SESSAO)
    assert h.resumo()["primeiros"]["sistemas_descobertos"] == 1


def test_exploracao_a_bordo_conta_sistemas_e_corpos_escaneados():
    h = historico_vazio()
    for i in (1, 2):
        h.consumir(scan(i), SESSAO)
    h.consumir(scan(1, sistema="Outro", sa=222), SESSAO)
    h.consumir(scan(1), SESSAO)  # repetido nao conta de novo
    a = h.resumo()["a_bordo"]
    assert (a["sistemas_exploracao"], a["corpos_exploracao"]) == (2, 3)


def test_resumo_ja_traz_campos_de_venda_e_morte_vazios():
    r = historico_vazio().resumo()
    assert r["vendido"] == {"amostras": [], "quantidade": 0, "total": 0, "exploracao_total": 0}
    assert r["perdido"] == {"amostras": 0, "sistemas": 0}
    assert r["medias"] == {"por_amostra": None, "por_planeta": None, "por_sessao": None}
    assert r["carreira"] is None


def test_evento_desconhecido_e_ignorado():
    historico_vazio().consumir({"event": "Music"}, SESSAO)


# ---- Task 3: vendas, morte e médias ----

ID_ACIES = "$Codex_Ent_Bacterial_04_Name;"
ID_OUTRA = "$Codex_Ent_Bacterial_05_Name;"


def analisa(h, especie="Bacterium Acies", especie_id=ID_ACIES, body=7, sessao=SESSAO,
            quando="2026-11-14T11:00:00Z", pisado=False, sa=SA):
    """Escaneia o corpo e registra uma Analyse."""
    h.consumir(scan(body, pisado=pisado, sa=sa), sessao)
    ev = organico("Analyse", body=body, especie=especie, quando=quando, sa=sa)
    ev["Species"] = especie_id
    h.consumir(ev, sessao)


def historico_com_analyse(especie="Bacterium Acies", corpo_nao_pisado=True):
    h = historico_vazio({"Bacterium Acies": 1_000_000, "Outra Especie": 500_000})
    analisa(h, especie=especie, pisado=not corpo_nao_pisado)
    return h


def item_venda(especie_id, especie, valor, bonus):
    return {"Genus": "$Codex_Ent_Bacterial_Genus_Name;", "Species": especie_id,
            "Species_Localised": especie, "Variant": "$x;",
            "Variant_Localised": f"{especie} - Verde",
            "Value": valor, "Bonus": bonus}


def venda_organica(itens, quando="2026-11-14T15:00:00Z"):
    return {"timestamp": quando, "event": "SellOrganicData",
            "BioData": [item_venda(i, e, v, b) for i, e, v, b in itens]}


def test_venda_tira_a_amostra_de_bordo_e_registra_o_valor_real():
    h = historico_com_analyse("Bacterium Acies", corpo_nao_pisado=True)
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 4_000_000)]), "s2")
    r = h.resumo()
    assert r["a_bordo"]["amostras"] == []
    [v] = r["vendido"]["amostras"]
    assert (v["valor"], v["bonus_pago"], v["previsao"], v["acertou"]) == (5_000_000, 4_000_000, "provavel", True)
    assert v["quando"] == "2026-11-14T15:00:00Z"
    assert v["sessao"] == SESSAO
    assert v["corpo"] == "Sis 7" and v["sistema"] == "Sis"
    assert r["vendido"]["total"] == 5_000_000


def test_venda_erra_a_previsao_quando_nao_houve_bonus():
    h = historico_com_analyse(corpo_nao_pisado=True)
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 0)]), SESSAO)
    [v] = h.resumo()["vendido"]["amostras"]
    assert (v["previsao"], v["acertou"]) == ("provavel", False)


def test_previsao_desconhecida_nao_tem_acerto():
    h = historico_vazio()
    h.consumir(organico("Analyse", body=99), SESSAO)   # corpo sem Scan -> desconhecido
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 0)]), SESSAO)
    [v] = h.resumo()["vendido"]["amostras"]
    assert (v["previsao"], v["acertou"]) == ("desconhecido", None)


def test_venda_casa_pela_amostra_mais_antiga_da_mesma_especie():
    h = historico_vazio({"Bacterium Acies": 1_000_000, "Outra Especie": 500_000})
    analisa(h, body=1, quando="2026-11-14T10:00:00Z")
    analisa(h, especie="Outra Especie", especie_id=ID_OUTRA, body=2, quando="2026-11-14T10:30:00Z")
    analisa(h, body=3, quando="2026-11-14T11:00:00Z")
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 4_000_000)]), SESSAO)
    r = h.resumo()
    [v] = r["vendido"]["amostras"]
    assert v["corpo"] == "Sis 1"
    restantes = [(a["especie"], a["corpo"]) for a in r["a_bordo"]["amostras"]]
    assert restantes == [("Outra Especie", "Sis 2"), ("Bacterium Acies", "Sis 3")]


def test_venda_sem_par_entra_sem_planeta():
    h = historico_vazio()
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 4_000_000)]), SESSAO)
    r = h.resumo()
    [v] = r["vendido"]["amostras"]
    assert v["especie"] == "Bacterium Acies"
    assert v["variante"] == "Bacterium Acies - Verde"
    assert v["corpo"] is None and v["sistema"] is None
    assert v["previsao"] is None and v["acertou"] is None and v["sessao"] is None
    assert r["vendido"]["total"] == 5_000_000


def test_venda_sem_par_e_sem_variante_localizada():
    h = historico_vazio()
    ev = venda_organica([(ID_ACIES, "Bacterium Acies", 1, 0)])
    del ev["BioData"][0]["Variant_Localised"]
    h.consumir(ev, SESSAO)
    assert h.resumo()["vendido"]["amostras"][0]["variante"] == ""


def test_morte_perde_amostras_e_dados_de_exploracao_a_bordo():
    h = historico_vazio()
    analisa(h, body=1)
    analisa(h, body=2)
    h.consumir(scan(1, sistema="Outro", sa=222), SESSAO)
    h.consumir({"timestamp": "2026-11-14T16:00:00Z", "event": "Died"}, SESSAO)
    r = h.resumo()
    assert r["perdido"] == {"amostras": 2, "sistemas": 2}
    assert r["a_bordo"]["amostras"] == []
    assert r["a_bordo"]["sistemas_exploracao"] == 0
    assert r["a_bordo"]["corpos_exploracao"] == 0
    h.consumir({"timestamp": "2026-11-14T16:05:00Z", "event": "Died"}, SESSAO)
    assert h.resumo()["perdido"] == {"amostras": 2, "sistemas": 2}


def test_venda_de_exploracao_tira_os_sistemas_de_bordo_e_soma_o_total():
    h = historico_vazio()
    h.consumir(scan(1, sistema="A", sa=1), SESSAO)
    h.consumir(scan(1, sistema="B", sa=2), SESSAO)
    h.consumir(scan(1, sistema="C", sa=3), SESSAO)
    h.consumir({"timestamp": "t", "event": "SellExplorationData", "Systems": ["A"],
                "Discovered": 1, "BaseValue": 10, "Bonus": 0, "TotalEarnings": 12_345}, SESSAO)
    r = h.resumo()
    assert r["a_bordo"]["sistemas_exploracao"] == 2
    assert r["vendido"]["exploracao_total"] == 12_345
    h.consumir({"timestamp": "t", "event": "MultiSellExplorationData",
                "Discovered": [{"SystemName": "B", "NumBodies": 1}], "TotalEarnings": 1_000}, SESSAO)
    r = h.resumo()
    assert r["a_bordo"]["sistemas_exploracao"] == 1
    assert r["vendido"]["exploracao_total"] == 13_345


def test_medias_ignoram_perdidas_e_amostras_sem_preco():
    h = historico_vazio({"Bacterium Acies": 1_000_000})
    analisa(h, body=1, sessao="s1")                                         # 5M estimados
    analisa(h, especie="Sem Preco", especie_id="$x;", body=2, sessao="s1")  # sem valor: fora
    analisa(h, body=3, sessao="s2", pisado=True)                            # 1M estimado
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 0)]), "s2")
    # a venda leva a mais antiga (Sis 1, sessão s1) por 1M reais; a bordo fica Sis 3 (1M, s2)
    m = h.resumo()["medias"]
    assert m["por_amostra"] == 1_000_000
    assert m["por_planeta"] == 1_000_000
    assert m["por_sessao"] == 1_000_000


def test_medias_por_planeta_e_sessao_agrupam_corretamente():
    h = historico_vazio()
    analisa(h, body=1, sessao="s1")                  # 5M, planeta 1, s1
    analisa(h, body=1, sessao="s1")                  # 5M, mesmo planeta e sessão
    analisa(h, body=2, sessao="s2", pisado=True)     # 1M, planeta 2, s2
    m = h.resumo()["medias"]
    assert m["por_amostra"] == round(11_000_000 / 3)
    assert m["por_planeta"] == 5_500_000    # 11M / 2 planetas
    assert m["por_sessao"] == 5_500_000     # 11M / 2 sessões


def test_medias_com_vendida_sem_par_entram_so_em_por_amostra():
    h = historico_vazio()
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 0)]), SESSAO)
    m = h.resumo()["medias"]
    assert m["por_amostra"] == 1_000_000
    assert m["por_planeta"] is None and m["por_sessao"] is None


def test_medias_sem_dados_sao_none():
    h = historico_vazio()
    assert h.resumo()["medias"] == {"por_amostra": None, "por_planeta": None, "por_sessao": None}


def test_morte_nao_entra_nas_medias():
    h = historico_vazio()
    analisa(h, body=1)
    h.consumir({"timestamp": "t", "event": "Died"}, SESSAO)
    assert h.resumo()["medias"]["por_amostra"] is None


def test_resumo_devolve_copias_e_mutar_nao_corrompe_o_historico():
    h = historico_vazio()
    analisa(h, body=1)
    h.consumir({"timestamp": "t", "event": "Statistics", "Exobiology": {"Organic_Genus_Encountered": 3}}, SESSAO)
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1, 0)]), SESSAO)
    analisa(h, body=2)
    r = h.resumo()
    r["a_bordo"]["amostras"][0]["especie"] = "CORROMPIDO"
    r["a_bordo"]["amostras"].append({"x": 1})
    r["vendido"]["amostras"][0]["valor"] = -1
    r["carreira"]["Organic_Genus_Encountered"] = 999
    r2 = h.resumo()
    assert r2["a_bordo"]["amostras"][0]["especie"] == "Bacterium Acies"
    assert len(r2["a_bordo"]["amostras"]) == 1
    assert r2["vendido"]["amostras"][0]["valor"] == 1
    assert r2["carreira"]["Organic_Genus_Encountered"] == 3


# ---- Onda final: limites, morte, campos Was* ausentes ----

def morre(h, quando="2026-11-14T16:00:00Z"):
    h.consumir({"timestamp": quando, "event": "Died"}, SESSAO)


def saa(h, body, sa=SA):
    h.consumir({"timestamp": "t", "event": "SAAScanComplete", "SystemAddress": sa,
                "BodyID": body}, SESSAO)


def pisa(h, body, sa=SA):
    h.consumir({"timestamp": "t", "event": "Disembark", "OnPlanet": True,
                "SystemAddress": sa, "BodyID": body}, SESSAO)


def scan_em(body_id, quando, **kw):
    ev = scan(body_id, **kw)
    ev["timestamp"] = quando
    return ev


def test_primeiros_lista_no_maximo_50_corpos_mais_recentes_primeiro():
    h = historico_vazio()
    for i in range(60):
        h.consumir(scan_em(i, f"2026-11-14T10:{i:02d}:00Z"), SESSAO)
    p = h.resumo()["primeiros"]
    assert exploracao.LIMITE_LISTA == 50
    assert len(p["corpos"]) == 50
    assert p["corpos"][0]["corpo"] == "Sis 59"
    assert p["corpos"][-1]["corpo"] == "Sis 10"
    assert p["corpos_descobertos"] == 60
    assert p["total_corpos"] == 60


def test_vendido_lista_no_maximo_50_vendas_mais_recentes_primeiro():
    h = historico_vazio()
    for i in range(60):
        h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000 + i, 0)],
                                  quando=f"2026-11-14T10:{i:02d}:00Z"), SESSAO)
    r = h.resumo()
    v = r["vendido"]
    assert len(v["amostras"]) == 50
    assert v["amostras"][0]["valor"] == 1_059
    assert v["amostras"][-1]["valor"] == 1_010
    assert v["quantidade"] == 60
    assert v["total"] == sum(1_000 + i for i in range(60))
    assert r["medias"]["por_amostra"] == round(sum(1_000 + i for i in range(60)) / 60)


def test_a_bordo_nao_tem_limite():
    h = historico_vazio()
    for i in range(60):
        h.consumir(organico("Analyse", body=i), SESSAO)
    assert len(h.resumo()["a_bordo"]["amostras"]) == 60


def test_morte_tira_o_credito_de_descoberta_e_mapeamento_a_bordo():
    h = historico_vazio()
    h.consumir(scan(0, dist=0.0), SESSAO)
    h.consumir(scan(3), SESSAO)
    saa(h, 3)
    morre(h)
    p = h.resumo()["primeiros"]
    assert p["corpos"] == []
    assert (p["sistemas_descobertos"], p["corpos_descobertos"], p["mapeados"]) == (0, 0, 0)


def test_morte_depois_de_vender_a_exploracao_mantem_o_credito():
    h = historico_vazio()
    h.consumir(scan(0, dist=0.0), SESSAO)
    h.consumir(scan(3), SESSAO)
    saa(h, 3)
    h.consumir({"timestamp": "t", "event": "SellExplorationData", "Systems": ["Sis"],
                "TotalEarnings": 10}, SESSAO)
    morre(h)
    p = h.resumo()["primeiros"]
    assert (p["sistemas_descobertos"], p["corpos_descobertos"], p["mapeados"]) == (1, 2, 1)


def test_morte_mantem_o_pisou():
    h = historico_vazio()
    h.consumir(scan(3), SESSAO)
    pisa(h, 3)
    morre(h)
    [c] = h.resumo()["primeiros"]["corpos"]
    assert (c["descobriu"], c["mapeou"], c["pisou"]) == (False, False, True)


def test_reescanear_depois_da_morte_reavalia_pelo_novo_scan():
    h = historico_vazio()
    h.consumir(scan(0, dist=0.0), SESSAO)
    h.consumir(scan(3), SESSAO)
    h.consumir(scan(4), SESSAO)
    morre(h)
    h.consumir(scan(0, dist=0.0), SESSAO)         # ainda não descoberto: o crédito volta
    h.consumir(scan(3, descoberto=True), SESSAO)  # alguém vendeu antes: vale este Scan novo
    h.consumir(scan(3), SESSAO)                   # e um Scan seguinte não o substitui
    h.consumir(scan(4), SESSAO)
    saa(h, 4)
    p = h.resumo()["primeiros"]
    assert p["sistemas_descobertos"] == 1
    corpos = {c["corpo"]: c for c in p["corpos"]}
    assert corpos["Sis 0"]["descobriu"] is True
    assert "Sis 3" not in corpos
    assert (corpos["Sis 4"]["descobriu"], corpos["Sis 4"]["mapeou"]) == (True, True)


def scan_sem_was(body_id, dist=10.0):
    ev = scan(body_id, dist=dist)
    for campo in ("WasDiscovered", "WasMapped", "WasFootfalled"):
        del ev[campo]
    return ev


def test_scan_sem_campos_was_nao_conta_como_primeiro():
    h = historico_vazio()
    h.consumir(scan_sem_was(0, dist=0.0), SESSAO)
    saa(h, 0)
    pisa(h, 0)
    p = h.resumo()["primeiros"]
    assert p["corpos"] == []
    assert (p["sistemas_descobertos"], p["corpos_descobertos"],
            p["mapeados"], p["pisados"]) == (0, 0, 0, 0)


def test_amostra_em_corpo_sem_was_footfalled_tem_bonus_desconhecido():
    h = historico_vazio()
    h.consumir(scan_sem_was(7), SESSAO)
    h.consumir(organico("Analyse", body=7), SESSAO)
    [a] = h.resumo()["a_bordo"]["amostras"]
    assert a["bonus"] == "desconhecido"
    assert a["valor_estimado"] == 1_000_000


def test_previsao_improvavel_com_bonus_pago_erra():
    h = historico_com_analyse(corpo_nao_pisado=False)
    h.consumir(venda_organica([(ID_ACIES, "Bacterium Acies", 1_000_000, 4_000_000)]), SESSAO)
    [v] = h.resumo()["vendido"]["amostras"]
    assert (v["previsao"], v["acertou"]) == ("improvavel", False)
