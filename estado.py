"""Estado vivo do cliente: o monitor escreve, o painel lê."""

import datetime
import threading

MAX_ERROS_PADRAO = 20


def _agora():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(momento):
    return momento.isoformat() if momento else None


class EstadoCliente:
    """Compartilhado entre a thread do monitor e a do painel, então protegido
    por um lock. As escritas são raras (uma por ciclo de 60 s) e as leituras
    também (uma a cada 5 s), então um lock simples basta."""

    def __init__(self, max_erros=MAX_ERROS_PADRAO):
        self._lock = threading.Lock()
        self._max_erros = max_erros
        self._journal_atual = None
        self._ultima_leitura = None
        self._ultimo_envio_ok = None
        self._ultimo_status_http = None
        self._instalacoes = []
        self._erros = []
        self._inicio = _agora()

    def registrar_leitura(self, journal, instalacoes):
        with self._lock:
            self._journal_atual = journal
            self._ultima_leitura = _agora()
            self._instalacoes = [
                {
                    "nome": i.nome,
                    "porcentagem": round(i.porcentagem, 1),
                    "materiais_faltando": sum(1 for m in i.materiais if not m.completo),
                    "total_faltando": sum(m.faltando for m in i.materiais if not m.completo),
                }
                for i in instalacoes
            ]

    def registrar_envio(self, nome, status_http):
        with self._lock:
            self._ultimo_status_http = status_http
            if 200 <= status_http < 300:
                self._ultimo_envio_ok = _agora()

    def registrar_erro(self, mensagem):
        with self._lock:
            self._erros.insert(0, {"quando": _iso(_agora()), "mensagem": str(mensagem)})
            del self._erros[self._max_erros :]

    def como_dicionario(self):
        with self._lock:
            return {
                "journal_atual": self._journal_atual,
                "ultima_leitura": _iso(self._ultima_leitura),
                "ultimo_envio_ok": _iso(self._ultimo_envio_ok),
                "ultimo_status_http": self._ultimo_status_http,
                "instalacoes": list(self._instalacoes),
                "erros": list(self._erros),
                "desde": _iso(self._inicio),
            }
