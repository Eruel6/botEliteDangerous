"""Estado do bot em SQLite.

O Render hiberna o serviço no plano gratuito e o processo perde tudo que estava
em memória. Guardando aqui o id da mensagem de cada instalação, o bot reencontra
a própria mensagem depois de acordar em vez de postar uma nova.
"""

import datetime
import json
import os
import sqlite3
from dataclasses import dataclass

import ed_parser

CAMINHO_PADRAO = "estado.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS instalacoes (
    nome                TEXT PRIMARY KEY,
    message_id          INTEGER NOT NULL,
    materiais           TEXT    NOT NULL,
    ultima_atualizacao  TEXT    NOT NULL,
    finalizado          INTEGER NOT NULL DEFAULT 0
)
"""

ESQUEMA_META = """
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
)
"""

ESQUEMA_CARGA = """
CREATE TABLE IF NOT EXISTS carga (
    quem       TEXT    NOT NULL,
    material   TEXT    NOT NULL,
    quantidade INTEGER NOT NULL,
    alvo       INTEGER,
    sistema    TEXT    NOT NULL DEFAULT '',
    quando     TEXT    NOT NULL,
    PRIMARY KEY (quem, material)
)
"""

ESQUEMA_ENTREGAS = """
CREATE TABLE IF NOT EXISTS entregas (
    quando     TEXT    NOT NULL,
    market_id  INTEGER NOT NULL,
    material   TEXT    NOT NULL,
    quem       TEXT    NOT NULL,
    quantidade INTEGER NOT NULL,
    PRIMARY KEY (quando, market_id, material, quem)
)
"""


@dataclass
class Registro:
    instalacao: ed_parser.Instalacao
    message_id: int
    ultima_atualizacao: datetime.datetime
    finalizado: bool
    reportado_por: str = ""


def _agora():
    return datetime.datetime.now(datetime.timezone.utc)


COLUNAS_NOVAS = {
    "market_id": "INTEGER",
    "reportado_por": "TEXT NOT NULL DEFAULT ''",
    "sistema": "TEXT NOT NULL DEFAULT ''",
}


class Armazenamento:
    def __init__(self, caminho=None):
        # A env é lida aqui, não no import: o servidor define CAMINHO_DB
        # depois que este módulo já foi carregado.
        self.caminho = caminho or os.getenv("CAMINHO_DB", CAMINHO_PADRAO)
        self._conexao = sqlite3.connect(self.caminho)
        self._conexao.row_factory = sqlite3.Row
        self._conexao.execute(ESQUEMA)
        self._conexao.execute(ESQUEMA_META)
        self._conexao.execute(ESQUEMA_CARGA)
        self._conexao.execute(ESQUEMA_ENTREGAS)
        self._migrar()
        self._conexao.commit()

    def _migrar(self):
        """Acrescenta colunas que faltam, sem recriar a tabela.

        Já existe banco em produção; recriar perderia o que está lá."""
        existentes = {
            l["name"] for l in self._conexao.execute("PRAGMA table_info(instalacoes)")
        }
        for coluna, tipo in COLUNAS_NOVAS.items():
            if coluna not in existentes:
                self._conexao.execute(
                    f"ALTER TABLE instalacoes ADD COLUMN {coluna} {tipo}"
                )

    def salvar(self, instalacao, message_id, quando=None, reportado_por=""):
        materiais = [
            {
                "Name_Localised": m.nome,
                "Name": m.nome_interno,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in instalacao.materiais
        ]

        # Deletar linhas com o mesmo market_id mas nome diferente para garantir
        # que existe apenas uma linha por market_id (a arbitragem é chaveada por market_id).
        if instalacao.market_id is not None:
            self._conexao.execute(
                "DELETE FROM instalacoes WHERE market_id = ? AND nome != ?",
                (instalacao.market_id, instalacao.nome),
            )

        self._conexao.execute(
            "INSERT INTO instalacoes "
            "(nome, message_id, materiais, ultima_atualizacao, finalizado, market_id, "
            "reportado_por, sistema) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?) "
            "ON CONFLICT(nome) DO UPDATE SET "
            "message_id=excluded.message_id, materiais=excluded.materiais, "
            "ultima_atualizacao=excluded.ultima_atualizacao, finalizado=0, "
            "market_id=excluded.market_id, reportado_por=excluded.reportado_por, "
            "sistema=excluded.sistema",
            (
                instalacao.nome,
                message_id,
                json.dumps(materiais, ensure_ascii=False),
                (quando or _agora()).isoformat(),
                instalacao.market_id,
                reportado_por,
                instalacao.sistema,
            ),
        )
        self._conexao.commit()

    def obter(self, chave, nome=None):
        """Procura por market_id quando ``chave`` é número, senão por nome.

        Quando a busca por market_id não acha nada e ``nome`` foi informado,
        cai para a busca por nome. Isso cobre o registro que a reconciliação
        do canal cria com market_id=None (a mensagem do Discord não carrega o
        MarketID) — sem essa queda, obter(market_id) nunca encontra esse
        registro e a mensagem antiga fica órfã no canal. `salvar` já garante
        no máximo uma linha por market_id, então a queda é segura.
        """
        if isinstance(chave, int):
            linha = self._conexao.execute(
                "SELECT * FROM instalacoes WHERE market_id = ?", (chave,)
            ).fetchone()
            if linha:
                return self._para_registro(linha)
            if nome is not None:
                linha = self._conexao.execute(
                    "SELECT * FROM instalacoes WHERE nome = ?", (nome,)
                ).fetchone()
                return self._para_registro(linha) if linha else None
            return None

        linha = self._conexao.execute(
            "SELECT * FROM instalacoes WHERE nome = ?", (chave,)
        ).fetchone()
        return self._para_registro(linha) if linha else None

    def listar(self, pendentes=False):
        sql = "SELECT * FROM instalacoes"
        if pendentes:
            sql += " WHERE finalizado = 0"
        return [self._para_registro(l) for l in self._conexao.execute(sql)]

    def marcar_finalizado(self, nome):
        self._conexao.execute("UPDATE instalacoes SET finalizado = 1 WHERE nome = ?", (nome,))
        self._conexao.commit()

    def obter_meta(self, chave, padrao=None):
        linha = self._conexao.execute(
            "SELECT valor FROM meta WHERE chave = ?", (chave,)
        ).fetchone()
        return linha["valor"] if linha else padrao

    def definir_meta(self, chave, valor):
        self._conexao.execute(
            "INSERT INTO meta (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, str(valor)),
        )
        self._conexao.commit()

    def substituir_carga(self, quem, itens, alvo, sistema, quando=None):
        """Troca o porão inteiro dessa pessoa. Sem delta: o retrato manda."""
        momento = (quando or _agora()).isoformat()
        self._conexao.execute("DELETE FROM carga WHERE quem = ?", (quem,))
        self._conexao.executemany(
            "INSERT INTO carga (quem, material, quantidade, alvo, sistema, quando) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (quem, material, int(quantidade), alvo, sistema, momento)
                for material, quantidade in itens.items()
                if int(quantidade) > 0
            ],
        )
        self._conexao.commit()

    def listar_carga(self, desde=None):
        """Linhas de carga; com ``desde``, só as relatadas a partir daquele momento."""
        sql = "SELECT * FROM carga"
        parametros = ()
        if desde is not None:
            sql += " WHERE quando >= ?"
            parametros = (desde.isoformat(),)
        return [dict(l) for l in self._conexao.execute(sql, parametros)]

    def registrar_entregas(self, quem, entregas):
        """Grava o que ainda não estava lá. Devolve quantas entraram.

        O cliente reenvia a sessão inteira a cada ciclo; a chave primária
        composta é o que torna isso barato em vez de destrutivo.
        """
        antes = self._conexao.total_changes
        self._conexao.executemany(
            "INSERT OR IGNORE INTO entregas "
            "(quando, market_id, material, quem, quantidade) VALUES (?, ?, ?, ?, ?)",
            [
                (e["quando"], e["market_id"], e["material"], quem, int(e["quantidade"]))
                for e in entregas
            ],
        )
        self._conexao.commit()
        return self._conexao.total_changes - antes

    def entregas_por_pessoa(self, market_id):
        """{quem: toneladas entregues} naquela obra."""
        return {
            l["quem"]: l["total"]
            for l in self._conexao.execute(
                "SELECT quem, SUM(quantidade) AS total FROM entregas "
                "WHERE market_id = ? GROUP BY quem",
                (market_id,),
            )
        }

    def remover(self, nome):
        self._conexao.execute("DELETE FROM instalacoes WHERE nome = ?", (nome,))
        self._conexao.commit()

    def fechar(self):
        self._conexao.close()

    @staticmethod
    def _para_registro(linha):
        chaves = linha.keys()
        return Registro(
            instalacao=ed_parser.instalacao_de_payload(
                linha["nome"],
                json.loads(linha["materiais"]),
                market_id=linha["market_id"] if "market_id" in chaves else None,
                sistema=(linha["sistema"] if "sistema" in chaves else "") or "",
            ),
            message_id=linha["message_id"],
            ultima_atualizacao=datetime.datetime.fromisoformat(linha["ultima_atualizacao"]),
            finalizado=bool(linha["finalizado"]),
            reportado_por=(linha["reportado_por"] if "reportado_por" in chaves else "") or "",
        )
