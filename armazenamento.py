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


def _agora():
    return datetime.datetime.now(datetime.timezone.utc)


class Armazenamento:
    def __init__(self, caminho=None):
        # A env é lida aqui, não no import: o servidor define CAMINHO_DB
        # depois que este módulo já foi carregado.
        self.caminho = caminho or os.getenv("CAMINHO_DB", CAMINHO_PADRAO)
        self._conexao = sqlite3.connect(self.caminho)
        self._conexao.row_factory = sqlite3.Row
        self._conexao.execute(ESQUEMA)
        self._conexao.commit()

    def salvar(self, instalacao, message_id, quando=None):
        materiais = [
            {
                "Name_Localised": m.nome,
                "Name": m.nome_interno,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in instalacao.materiais
        ]
        self._conexao.execute(
            "INSERT INTO instalacoes (nome, message_id, materiais, ultima_atualizacao, finalizado) "
            "VALUES (?, ?, ?, ?, 0) "
            "ON CONFLICT(nome) DO UPDATE SET "
            "message_id=excluded.message_id, materiais=excluded.materiais, "
            "ultima_atualizacao=excluded.ultima_atualizacao, finalizado=0",
            (
                instalacao.nome,
                message_id,
                json.dumps(materiais, ensure_ascii=False),
                (quando or _agora()).isoformat(),
            ),
        )
        self._conexao.commit()

    def obter(self, nome):
        linha = self._conexao.execute(
            "SELECT * FROM instalacoes WHERE nome = ?", (nome,)
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
        return Registro(
            instalacao=ed_parser.instalacao_de_payload(
                linha["nome"], json.loads(linha["materiais"])
            ),
            message_id=linha["message_id"],
            ultima_atualizacao=datetime.datetime.fromisoformat(linha["ultima_atualizacao"]),
            finalizado=bool(linha["finalizado"]),
        )
