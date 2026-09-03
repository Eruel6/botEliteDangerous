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
}


class Armazenamento:
    def __init__(self, caminho=None):
        # A env é lida aqui, não no import: o servidor define CAMINHO_DB
        # depois que este módulo já foi carregado.
        self.caminho = caminho or os.getenv("CAMINHO_DB", CAMINHO_PADRAO)
        self._conexao = sqlite3.connect(self.caminho)
        self._conexao.row_factory = sqlite3.Row
        self._conexao.execute(ESQUEMA)
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
            "(nome, message_id, materiais, ultima_atualizacao, finalizado, market_id, reportado_por) "
            "VALUES (?, ?, ?, ?, 0, ?, ?) "
            "ON CONFLICT(nome) DO UPDATE SET "
            "message_id=excluded.message_id, materiais=excluded.materiais, "
            "ultima_atualizacao=excluded.ultima_atualizacao, finalizado=0, "
            "market_id=excluded.market_id, reportado_por=excluded.reportado_por",
            (
                instalacao.nome,
                message_id,
                json.dumps(materiais, ensure_ascii=False),
                (quando or _agora()).isoformat(),
                instalacao.market_id,
                reportado_por,
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
            ),
            message_id=linha["message_id"],
            ultima_atualizacao=datetime.datetime.fromisoformat(linha["ultima_atualizacao"]),
            finalizado=bool(linha["finalizado"]),
            reportado_por=(linha["reportado_por"] if "reportado_por" in chaves else "") or "",
        )
