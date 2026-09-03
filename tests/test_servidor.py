"""Testes do servidor que não precisam de conexão real com o Discord."""

import asyncio
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


@pytest.fixture
def servidor(monkeypatch, tmp_path):
    """Servidor recarregado com um banco próprio, isolado por teste."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-de-teste")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "estado.db"))
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor as mod

    return mod


def test_importa_sem_event_loop_corrente(monkeypatch, tmp_path):
    """Em Python 3.12+ não existe loop corrente na importação.

    asyncio.set_event_loop(None) reproduz essa condição em qualquer versão.
    """
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-de-teste")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "estado.db"))
    sys.modules.pop("armazenamento", None)
    asyncio.set_event_loop(None)
    try:
        sys.modules.pop("servidor", None)
        import servidor  # noqa: F401
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())


class ReacaoFalsa:
    def __init__(self, emoji):
        self.emoji = emoji


class MensagemFalsa:
    """Imita discord.Message: reactions é uma lista, não um iterador assíncrono."""

    def __init__(self, reactions=()):
        self.reactions = list(reactions)
        self.reacoes_adicionadas = []

    async def add_reaction(self, emoji):
        self.reacoes_adicionadas.append(emoji)
        self.reactions.append(ReacaoFalsa(emoji))


def test_marca_check_quando_todos_os_materiais_foram_entregues(servidor):
    import ed_parser

    instalacao = ed_parser.instalacao_de_payload(
        "X", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 10}]
    )
    mensagem = MensagemFalsa()

    asyncio.run(servidor.adicionar_reacao_check(mensagem, instalacao.materiais))

    assert mensagem.reacoes_adicionadas == ["✅"]


def test_nao_duplica_o_check_se_ja_estiver_na_mensagem(servidor):
    import ed_parser

    instalacao = ed_parser.instalacao_de_payload(
        "X", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 10}]
    )
    mensagem = MensagemFalsa([ReacaoFalsa("✅")])

    asyncio.run(servidor.adicionar_reacao_check(mensagem, instalacao.materiais))

    assert mensagem.reacoes_adicionadas == []


def test_nao_marca_check_com_material_faltando(servidor):
    import ed_parser

    instalacao = ed_parser.instalacao_de_payload(
        "X", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 9}]
    )
    mensagem = MensagemFalsa()

    asyncio.run(servidor.adicionar_reacao_check(mensagem, instalacao.materiais))

    assert mensagem.reacoes_adicionadas == []


# --- autenticação do endpoint -------------------------------------------------

CABECALHO = "X-API-Token"


@pytest.fixture
def cliente_http(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-de-teste")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("API_TOKEN", "segredo")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "estado.db"))
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    from fastapi.testclient import TestClient

    # TestClient dispara o lifespan (que conectaria no Discord); usamos a app crua.
    return TestClient(servidor.app, raise_server_exceptions=False)


PAYLOAD = {
    "instalacao": "Planetary Construction Site: X",
    "materiais": [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
}


def test_recusa_requisicao_sem_token(cliente_http):
    resposta = cliente_http.post("/logdata", json=PAYLOAD)
    assert resposta.status_code == 401


def test_recusa_requisicao_com_token_errado(cliente_http):
    resposta = cliente_http.post("/logdata", json=PAYLOAD, headers={CABECALHO: "chute"})
    assert resposta.status_code == 401


def test_token_correto_passa_da_autenticacao(cliente_http):
    """Com token válido não é mais 401 — para aqui porque o bot não está conectado."""
    resposta = cliente_http.post("/logdata", json=PAYLOAD, headers={CABECALHO: "segredo"})
    assert resposta.status_code == 503


def test_endpoint_desabilitado_quando_API_TOKEN_nao_esta_configurado(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-de-teste")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKENS", raising=False)
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "estado.db"))
    sys.modules.pop("servidor", None)
    import servidor

    from fastapi.testclient import TestClient

    resposta = TestClient(servidor.app).post("/logdata", json=PAYLOAD, headers={CABECALHO: "x"})
    assert resposta.status_code == 503
    assert "API_TOKEN" in resposta.json()["detail"]


# --- reconstrução do estado a partir do canal --------------------------------


class CanalFalso:
    """Imita discord.TextChannel para os poucos métodos que o servidor usa."""

    def __init__(self, mensagens=(), bot=None):
        self._mensagens = list(mensagens)
        self.bot = bot

    def history(self, limit=None):
        async def gerar():
            for m in self._mensagens[:limit]:
                yield m

        return gerar()

    async def fetch_message(self, message_id):
        import discord

        for m in self._mensagens:
            if m.id == message_id:
                return m
        raise discord.NotFound(_RespostaFalsa(), "nao existe")


class _RespostaFalsa:
    status = 404
    reason = "Not Found"


class UsuarioFalso:
    """discord.py devolve ClientUser em client.user e User em message.author:
    objetos distintos para o mesmo bot, comparáveis só pelo id."""

    def __init__(self, id):
        self.id = id

    def __eq__(self, outro):
        return isinstance(outro, UsuarioFalso) and outro.id == self.id

    def __hash__(self):
        return hash(self.id)


class MensagemComConteudo(MensagemFalsa):
    def __init__(self, id, content, author):
        super().__init__()
        self.id = id
        self.content = content
        self.author = author


def test_reconstroi_o_estado_lendo_as_proprias_mensagens_do_canal(servidor, tmp_path):
    import ed_parser

    bot = UsuarioFalso(42)
    inst = ed_parser.instalacao_de_payload(
        "Planetary Construction Site: Pedder's Forge",
        [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
    )
    canal = CanalFalso(
        [
            MensagemComConteudo(
                555, ed_parser.formatar_mensagem_discord(inst, "40.0%"), UsuarioFalso(42)
            ),
            MensagemComConteudo(556, "papo aleatório do canal", UsuarioFalso(99)),
        ],
        bot=bot,
    )

    # autor é outro objeto com o mesmo id, como client.user vs message.author
    asyncio.run(servidor.reconciliar_com_o_canal(canal, autor=UsuarioFalso(42)))

    registro = servidor.banco.obter(inst.nome)
    assert registro.message_id == 555
    assert registro.instalacao.materiais[0].faltando == 6


def test_reconciliacao_ignora_mensagens_de_outros_autores(servidor):
    canal = CanalFalso([MensagemComConteudo(1, "papo", UsuarioFalso(99))], bot=UsuarioFalso(42))

    asyncio.run(servidor.reconciliar_com_o_canal(canal, autor=UsuarioFalso(42)))

    assert servidor.banco.listar() == []


def test_reconciliacao_nao_sobrescreve_registro_ja_conhecido(servidor):
    import ed_parser

    bot = UsuarioFalso(42)
    inst = ed_parser.instalacao_de_payload(
        "Planetary Construction Site: X",
        [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 10}],
    )
    servidor.banco.salvar(inst, message_id=111)
    canal = CanalFalso(
        [MensagemComConteudo(222, ed_parser.formatar_mensagem_discord(inst), bot)], bot=bot
    )

    asyncio.run(servidor.reconciliar_com_o_canal(canal, autor=bot))

    assert servidor.banco.obter(inst.nome).message_id == 111


def test_carrega_um_token_por_pessoa(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.setenv("API_TOKENS", "Arthur=aaa\nFulano=bbb\n")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    assert servidor.carregar_tokens() == {"aaa": "Arthur", "bbb": "Fulano"}


def test_api_token_sozinho_continua_valendo(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.delenv("API_TOKENS", raising=False)
    monkeypatch.setenv("API_TOKEN", "sozinho")
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    assert servidor.carregar_tokens() == {"sozinho": "desconhecido"}


@pytest.fixture
def servidor_multi(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.setenv("API_TOKENS", "Arthur=aaa\nFulano=bbb\n")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    return servidor


def test_token_conhecido_devolve_o_nome(servidor_multi):
    assert servidor_multi.conferir_token("bbb") == "Fulano"


def test_token_desconhecido_e_401(servidor_multi):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as erro:
        servidor_multi.conferir_token("chute")

    assert erro.value.status_code == 401


def test_sem_nenhum_token_configurado_e_503(monkeypatch, tmp_path):
    from fastapi import HTTPException

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.delenv("API_TOKENS", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    with pytest.raises(HTTPException) as erro:
        servidor.conferir_token("qualquer")

    assert erro.value.status_code == 503


def test_token_vazio_nao_eh_carregado(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.setenv("API_TOKENS", "Arthur=\n")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    assert servidor.carregar_tokens() == {}


def test_nome_vazio_nao_eh_carregado(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.setenv("API_TOKENS", "=abcdef\n")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    assert servidor.carregar_tokens() == {}


def test_token_vazio_nao_autentica_mesmo_com_nome(monkeypatch, tmp_path):
    from fastapi import HTTPException

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789012345678")
    monkeypatch.setenv("CAMINHO_DB", str(tmp_path / "e.db"))
    monkeypatch.setenv("API_TOKENS", "Arthur=\n")
    monkeypatch.delenv("API_TOKEN", raising=False)
    sys.modules.pop("servidor", None)
    sys.modules.pop("armazenamento", None)
    import servidor

    # Testa diretamente conferir_token, sem passar pelo endpoint
    # (evita interferência do client.is_ready()).
    # Com a linha "Arthur=" (token vazio) rejeitada, não há tokens válidos.
    # Tentativa de autenticar com None (header ausente) deve levantar 503.
    with pytest.raises(HTTPException) as erro:
        servidor.conferir_token(None)

    assert erro.value.status_code == 503
    assert "API_TOKENS" in erro.value.detail


def test_total_fornecido_soma_os_materiais(servidor):
    import ed_parser

    inst = ed_parser.instalacao_de_payload(
        "Obra",
        [
            {"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4},
            {"Name_Localised": "Alumínio", "RequiredAmount": 20, "ProvidedAmount": 6},
        ],
    )

    assert servidor.total_fornecido(inst) == 10


def test_relato_menos_completo_e_ignorado(servidor):
    import ed_parser

    guardado = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 8}],
        market_id=555,
    )
    servidor.banco.salvar(guardado, message_id=1, reportado_por="Arthur")

    chegando = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 3}],
        market_id=555,
    )

    assert servidor.deve_publicar(chegando) is False


def test_relato_mais_completo_e_publicado(servidor):
    import ed_parser

    guardado = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 3}],
        market_id=555,
    )
    servidor.banco.salvar(guardado, message_id=1)

    chegando = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 8}],
        market_id=555,
    )

    assert servidor.deve_publicar(chegando) is True


def test_relato_igual_e_ignorado(servidor):
    import ed_parser

    inst = ed_parser.instalacao_de_payload(
        "Obra", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 5}],
        market_id=555,
    )
    servidor.banco.salvar(inst, message_id=1)

    assert servidor.deve_publicar(inst) is False


def test_instalacao_nova_sempre_publica(servidor):
    import ed_parser

    inst = ed_parser.instalacao_de_payload(
        "Obra Nunca Vista", [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 0}],
        market_id=999,
    )

    assert servidor.deve_publicar(inst) is True
