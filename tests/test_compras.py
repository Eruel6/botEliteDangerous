import datetime
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ardent
import compras
import ed_parser

AGORA = datetime.datetime(2026, 9, 5, 12, 0, tzinfo=datetime.timezone.utc)


def _obra(nome, materiais, sistema="Sol"):
    return ed_parser.Instalacao(
        market_id=1,
        nome=nome,
        materiais=[
            ed_parser.Material(nome=n, nome_interno=i, requerido=r, fornecido=0)
            for n, i, r in materiais
        ],
        sistema=sistema,
    )


def _estacao(nome="Estacao"):
    return ardent.Estacao(
        nome=nome, sistema="Sol", distancia_ly=10, distancia_ls=100,
        estoque=9999, preco=100, pad=3, carrier=False,
        atualizado_em=AGORA.isoformat().replace("+00:00", "Z"),
    )


class ConsultaFalsa:
    def __init__(self, resultado=None):
        self.chamadas = []
        self.resultado = [_estacao()] if resultado is None else resultado

    def __call__(self, sistema, material, volume_minimo, raio=50):
        self.chamadas.append((sistema, material, volume_minimo))
        return self.resultado


def test_consulta_um_material_faltante():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)

    sugestoes = buscador.sugestoes([_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "Sol", AGORA)

    assert [s.material for s in sugestoes] == ["Alumínio"]
    assert consulta.chamadas == [("Sol", "aluminium", 180)]


def test_o_volume_minimo_e_um_quarto_do_porao():
    consulta = ConsultaFalsa()
    compras.Buscador("type9", 720, consultar=consulta).sugestoes(
        [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "Sol", AGORA
    )

    assert consulta.chamadas[0][2] == 180


def test_material_ja_completo_nao_e_consultado():
    consulta = ConsultaFalsa()
    obra = _obra("A", [("Alumínio", "$Aluminium_name;", 100)])
    obra.materiais[0].fornecido = 100

    compras.Buscador("type9", 720, consultar=consulta).sugestoes([obra], "Sol", AGORA)

    assert consulta.chamadas == []


def test_obra_sem_nome_interno_vira_sugestao_nao_consultavel():
    """Linha reconciliada do canal: só o nome localizado sobreviveu."""
    consulta = ConsultaFalsa()

    (sugestao,) = compras.Buscador("type9", 720, consultar=consulta).sugestoes(
        [_obra("A", [("Alumínio", "", 500)])], "Sol", AGORA
    )

    assert sugestao.consultavel is False
    assert sugestao.estacoes == []
    assert consulta.chamadas == []


def test_o_mesmo_material_em_duas_obras_e_uma_consulta_so():
    consulta = ConsultaFalsa()
    obras = [
        _obra("A", [("Alumínio", "$Aluminium_name;", 500)]),
        _obra("B", [("Alumínio", "$Aluminium_name;", 300)]),
    ]

    sugestoes = compras.Buscador("type9", 720, consultar=consulta).sugestoes(obras, "Sol", AGORA)

    assert len(consulta.chamadas) == 1
    assert sugestoes[0].faltando == 800


def test_o_cache_evita_a_segunda_consulta():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=5))

    assert len(consulta.chamadas) == 1


def test_o_cache_vence_depois_de_quinze_minutos():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=16))

    assert len(consulta.chamadas) == 2


def test_mudar_de_sistema_consulta_de_novo():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Outro", AGORA)

    assert [c[0] for c in consulta.chamadas] == ["Sol", "Outro"]


def test_falha_de_rede_mantem_o_ultimo_resultado_bom():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]
    buscador.sugestoes(obras, "Sol", AGORA)

    consulta.resultado = None  # a API sumiu
    depois = buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=16))

    assert [e.nome for e in depois[0].estacoes] == ["Estacao"]
    assert depois[0].desatualizado is True


def test_lista_vazia_nao_e_falha():
    consulta = ConsultaFalsa(resultado=[])
    buscador = compras.Buscador("type9", 720, consultar=consulta)

    (sugestao,) = buscador.sugestoes(
        [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "Sol", AGORA
    )

    assert sugestao.estacoes == []
    assert sugestao.desatualizado is False


def test_sem_sistema_corrente_nao_consulta_nada():
    consulta = ConsultaFalsa()

    sugestoes = compras.Buscador("type9", 720, consultar=consulta).sugestoes(
        [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])], "", AGORA
    )

    assert consulta.chamadas == []
    assert sugestoes == []


def test_falha_lembrada_nao_reconsulta_no_ciclo_seguinte():
    """Uma falha (404, timeout, JSON estranho) não pode virar reconsulta a cada ciclo."""
    consulta = ConsultaFalsa()
    consulta.resultado = None  # a API não sabe responder
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=1))

    assert len(consulta.chamadas) == 1


def test_falha_lembrada_reconsulta_apos_a_janela_expirar():
    consulta = ConsultaFalsa()
    consulta.resultado = None  # a API não sabe responder
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=6))

    assert len(consulta.chamadas) == 2


def test_falha_lembrada_ainda_serve_o_ultimo_resultado_bom():
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]
    buscador.sugestoes(obras, "Sol", AGORA)

    consulta.resultado = None  # a API sumiu
    depois_16 = buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=16))
    depois_17 = buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=17))

    assert [e.nome for e in depois_16[0].estacoes] == ["Estacao"]
    assert [e.nome for e in depois_17[0].estacoes] == ["Estacao"]
    assert depois_17[0].desatualizado is True
    # Uma consulta boa (t=0) e uma que falhou (t=16); t=17 não reconsultou.
    assert len(consulta.chamadas) == 2


def test_entrada_expirada_e_removida_do_cache():
    """Entrada expirada é descartada, não acumulada no cache."""
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Sol", AGORA + datetime.timedelta(minutes=16))

    assert len(buscador._cache) == 1


def test_entrada_expirada_em_sistema_diferente_nao_fica_residente():
    """Entrada expirada não é mantida quando outro sistema é consultado."""
    consulta = ConsultaFalsa()
    buscador = compras.Buscador("type9", 720, consultar=consulta)
    obras = [_obra("A", [("Alumínio", "$Aluminium_name;", 500)])]

    buscador.sugestoes(obras, "Sol", AGORA)
    buscador.sugestoes(obras, "Outro", AGORA + datetime.timedelta(minutes=16))

    assert len(buscador._cache) == 1
