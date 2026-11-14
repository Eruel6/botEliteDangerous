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
    assert r["vendido"] == {"amostras": [], "total": 0, "exploracao_total": 0}
    assert r["perdido"] == {"amostras": 0, "sistemas": 0}
    assert r["medias"] == {"por_amostra": None, "por_planeta": None, "por_sessao": None}
    assert r["carreira"] is None


def test_evento_desconhecido_e_ignorado():
    historico_vazio().consumir({"event": "Music"}, SESSAO)
