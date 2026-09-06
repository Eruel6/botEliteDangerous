import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import config_cliente
import ed_parser
import estado
import monitor

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BASICO = os.path.join(FIXTURES, "journal_basico.log")

CONFIG = config_cliente.Config(api_token="tok", api_url="https://exemplo/logdata")


def test_payload_inclui_o_market_id():
    (inst, _) = ed_parser.extrair_instalacoes(BASICO)

    payload = monitor.payload_de(inst)

    assert payload["market_id"] == 4251780355
    assert payload["instalacao"] == "Planetary Construction Site: Pedder's Forge"


def test_envio_que_falha_e_reenviado_no_ciclo_seguinte():
    tentativas = []

    def enviar_falhando(payload, config):
        tentativas.append(payload["instalacao"])
        return monitor.Resposta(500, "erro interno")

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_falhando)
    quantas_na_primeira = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_falhando)

    assert len(tentativas) == quantas_na_primeira * 2, "deveria ter reenviado tudo"


def test_envio_bem_sucedido_nao_e_reenviado():
    tentativas = []

    def enviar_ok(payload, config):
        tentativas.append(payload["instalacao"])
        return monitor.Resposta(200, '{"status":"ok"}')

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ok)
    quantas = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ok)

    assert len(tentativas) == quantas, "não deveria ter reenviado nada"


def test_relato_ignorado_pelo_servidor_conta_como_sucesso():
    """200 com status 'ignorado' significa que o servidor recebeu e decidiu.
    Reenviar seria um loop inútil."""
    tentativas = []

    def enviar_ignorado(payload, config):
        tentativas.append(payload["instalacao"])
        return monitor.Resposta(200, '{"status":"ignorado"}')

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ignorado)
    quantas = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ignorado)

    assert len(tentativas) == quantas


def test_registra_a_leitura_no_estado():
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e, enviar=lambda p, c: monitor.Resposta(200, ""))

    d = e.como_dicionario()
    assert d["journal_atual"] == BASICO
    assert len(d["instalacoes"]) == 2


def test_registra_erro_no_estado_quando_o_envio_falha():
    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO, {}, CONFIG, e, enviar=lambda p, c: monitor.Resposta(401, "Token inválido.")
    )

    erros = e.como_dicionario()["erros"]
    assert erros, "um 401 deveria virar erro visível"
    assert "401" in erros[0]["mensagem"]
    assert "Token inválido." in erros[0]["mensagem"]


def test_ignora_instalacao_desconhecida():
    enviados = []
    monitor.sincronizar(
        os.path.join(FIXTURES, "journal_sem_fonte_de_nome.log"),
        {},
        CONFIG,
        estado.EstadoCliente(),
        enviar=lambda p, c: enviados.append(p) or monitor.Resposta(200, ""),
    )

    assert enviados == []


def test_manda_o_token_e_a_url_da_config(monkeypatch):
    capturado = {}

    def post_falso(url, json=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["headers"] = headers

        class R:
            status_code = 200
            text = "ok"

        return R()

    monkeypatch.setattr(monitor.requests, "post", post_falso)

    monitor.enviar_para_api({"instalacao": "X"}, CONFIG)

    assert capturado["url"] == "https://exemplo/logdata"
    assert capturado["headers"]["X-API-Token"] == "tok"


def test_falha_de_rede_devolve_status_nulo_com_o_motivo(monkeypatch):
    def post_explodindo(*args, **kwargs):
        raise OSError("rede caiu")

    monkeypatch.setattr(monitor.requests, "post", post_explodindo)

    resposta = monitor.enviar_para_api({"instalacao": "X"}, CONFIG)

    assert resposta.status is None
    assert "rede caiu" in resposta.detalhe


def _resposta_falsa(status, texto, json_valido=None):
    class R:
        status_code = status
        text = texto

        def json(self):
            if json_valido is None:
                raise ValueError("não é JSON")
            return json_valido

    return R()


def test_detalhe_do_servidor_aparece_no_erro(monkeypatch):
    """Sem o corpo da resposta o painel não distingue os dois 503 possíveis:
    o bot ainda não pronto e o edge do Render acordando."""
    monkeypatch.setattr(
        monitor.requests,
        "post",
        lambda *a, **k: _resposta_falsa(
            503,
            '{"detail":"Bot do Discord ainda não está pronto."}',
            {"detail": "Bot do Discord ainda não está pronto."},
        ),
    )
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e)

    mensagem = e.como_dicionario()["erros"][0]["mensagem"]
    assert "503" in mensagem
    assert "Bot do Discord ainda não está pronto." in mensagem


def test_corpo_sem_json_entra_em_uma_linha_e_cortado(monkeypatch):
    """O edge do Render responde uma página HTML inteira quando o serviço está
    acordando. Ela não pode empurrar as outras linhas do painel para fora."""
    html = "<html>\n  <body>\n    " + ("acordando " * 200) + "\n  </body>\n</html>"
    monkeypatch.setattr(
        monitor.requests, "post", lambda *a, **k: _resposta_falsa(503, html)
    )
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e)

    mensagem = e.como_dicionario()["erros"][0]["mensagem"]
    assert "\n" not in mensagem, "o painel mostra uma linha por erro"
    assert len(mensagem) < 300, f"mensagem de {len(mensagem)} caracteres"
    assert "acordando" in mensagem


def test_falha_de_rede_diz_o_motivo(monkeypatch):
    """Um hostname errado no config já escondeu uma falha por semanas; o motivo
    da falha de rede precisa chegar ao painel."""
    def post_estourando(*a, **k):
        raise OSError("tempo esgotado depois de 30s")

    monkeypatch.setattr(monitor.requests, "post", post_estourando)
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e)

    mensagem = e.como_dicionario()["erros"][0]["mensagem"]
    assert "tempo esgotado depois de 30s" in mensagem


def test_a_url_do_comandante_sai_da_url_de_logdata():
    """O config.txt de quem já usa aponta para /logdata; derivar evita mexer nele."""
    assert (
        monitor.url_do_comandante("https://exemplo.onrender.com/logdata")
        == "https://exemplo.onrender.com/comandante"
    )


def test_o_payload_do_comandante_tem_carga_alvo_e_entregas():
    import comandante

    retrato = comandante.RetratoComandante(
        carga={"Alumínio": 720},
        alvo_market_id=901,
        alvo_sistema="Sol",
        entregas=[comandante.Entrega("2025-05-20T17:37:50Z", 901, "Alumínio", 720)],
    )

    payload = monitor.payload_do_comandante(retrato)

    assert payload["carga"] == [{"material": "Alumínio", "quantidade": 720}]
    assert payload["alvo"] == {"market_id": 901, "sistema": "Sol"}
    assert payload["entregas"][0]["quando"] == "2025-05-20T17:37:50Z"


def test_sincronizar_manda_o_retrato_uma_vez_por_ciclo():
    enviados = []
    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: enviados.append(r) or monitor.Resposta(200, ""),
    )

    assert len(enviados) == 1, "uma vez por ciclo, não uma por obra"


def test_falha_no_retrato_nao_derruba_o_ciclo():
    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(500, "explodiu"),
    )

    assert any("comandante" in erro["mensagem"] for erro in e.como_dicionario()["erros"])


def test_por_padrao_sincronizar_nao_manda_retrato():
    """Sem isso, todo teste que chama sincronizar faria requisição de rede."""
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e, enviar=lambda p, c: monitor.Resposta(200, ""))

    assert not any("comandante" in erro["mensagem"] for erro in e.como_dicionario()["erros"])


def test_o_ciclo_grava_as_compras_no_estado():
    import ardent
    import compras

    estacao = ardent.Estacao(
        nome="Nagasaki", sistema="Sol", distancia_ly=10, distancia_ls=100,
        estoque=9999, preco=127, pad=3, carrier=False, atualizado_em="2026-09-01T00:00:00Z",
    )

    class BuscadorFalso:
        def sugestoes(self, obras, sistema, agora):
            return [compras.SugestaoMaterial(material="Alumínio", faltando=500,
                                             estacoes=[estacao])]

    e = estado.EstadoCliente()
    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(200, ""),
        buscador=BuscadorFalso(),
    )

    (sugestao,) = e.como_dicionario()["compras"]
    assert sugestao["material"] == "Alumínio"
    assert sugestao["estacoes"][0]["nome"] == "Nagasaki"
    assert sugestao["estacoes"][0]["carrier"] is False


def test_o_ciclo_busca_pelo_sistema_do_piloto_nao_pela_obra():
    """journal_com_sistema.log: obra vista em A, piloto pula para B depois.

    A consulta de compras tem que seguir o piloto (B), não ficar presa no
    sistema da obra (A) como ``comandante.alvo_atual`` fica de propósito.
    """
    COM_SISTEMA = os.path.join(FIXTURES, "journal_com_sistema.log")

    class BuscadorEspiao:
        def __init__(self):
            self.sistemas_recebidos = []

        def sugestoes(self, obras, sistema, agora):
            self.sistemas_recebidos.append(sistema)
            return []

    buscador = BuscadorEspiao()
    e = estado.EstadoCliente()
    monitor.sincronizar(
        COM_SISTEMA, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(200, ""),
        buscador=buscador,
    )

    assert buscador.sistemas_recebidos == ["Outro Sistema"]


def test_sugestao_para_dicionario_serializa_a_hora_do_dado():
    import datetime

    import compras

    quando = datetime.datetime(2026, 9, 5, 14, 32, tzinfo=datetime.timezone.utc)
    sugestao = compras.SugestaoMaterial(material="Alumínio", faltando=500, desatualizado=True, quando=quando)

    assert monitor.sugestao_para_dicionario(sugestao)["quando"] == "2026-09-05T14:32:00+00:00"


def test_sugestao_para_dicionario_sem_hora_vira_none():
    import compras

    sugestao = compras.SugestaoMaterial(material="Alumínio", faltando=500, consultavel=False)

    assert monitor.sugestao_para_dicionario(sugestao)["quando"] is None


def test_sem_buscador_o_ciclo_nao_quebra():
    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(200, ""),
        buscador=None,
    )

    assert e.como_dicionario()["compras"] == []


def test_trocar_de_nave_atualiza_o_buscador():
    """Sair de uma nave pequena para o Type-9 muda o pad exigido e o porão."""
    import compras

    buscador = compras.Buscador("sidewinder", 4)
    buscador.nave, buscador.capacidade = "type9", 720

    assert buscador._volume_minimo() == 180


def test_falha_no_buscador_nao_derruba_o_ciclo():
    class BuscadorQueExplode:
        def sugestoes(self, obras, sistema, agora):
            raise RuntimeError("a API sumiu")

    e = estado.EstadoCliente()

    monitor.sincronizar(
        BASICO, {}, CONFIG, e,
        enviar=lambda p, c: monitor.Resposta(200, ""),
        enviar_retrato=lambda r, c: monitor.Resposta(200, ""),
        buscador=BuscadorQueExplode(),
    )

    assert any("compra" in erro["mensagem"] for erro in e.como_dicionario()["erros"])
