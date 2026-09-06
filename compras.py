"""Decide o que consultar no Ardent e guarda o resultado por um tempo.

O preço de uma estação não muda em 60 segundos, que é o ciclo do cliente. Sem
cache, uma dúzia de materiais faltando viraria uma dúzia de requisições por
minuto, por cliente, contra uma API pública e gratuita.
"""

import datetime
from dataclasses import dataclass, field

import ardent

VALIDADE_CACHE_MINUTOS = 15
FRACAO_MINIMA_DO_PORAO = 0.25

# Uma consulta que falhou (rede, timeout, 404, JSON estranho) fica "lembrada"
# por esse tempo, sem reconsultar. Sem isso, um sistema que o Ardent não
# conhece — ou uma API só lenta, não fora do ar — vira reconsulta a cada
# ciclo de 60 s, para sempre: com uma dúzia de materiais faltando e 30 s de
# timeout cada, um sincronizar() inteiro passa a levar minutos.
VALIDADE_FALHA_MINUTOS = 5


@dataclass
class SugestaoMaterial:
    material: str            # nome localizado, que é o que o painel mostra
    faltando: int
    estacoes: list = field(default_factory=list)
    consultavel: bool = True
    desatualizado: bool = False
    quando: datetime.datetime = None  # hora do dado mostrado; só importa se desatualizado


@dataclass
class _Entrada:
    estacoes: list
    quando: datetime.datetime


class Buscador:
    """Guarda o cache entre os ciclos. Um por processo de cliente."""

    def __init__(self, nave, capacidade, consultar=ardent.consultar):
        self.nave = nave
        self.capacidade = capacidade
        self._consultar = consultar
        self._cache = {}
        self._falhas = {}

    def _volume_minimo(self):
        return int(self.capacidade * FRACAO_MINIMA_DO_PORAO)

    def sugestoes(self, obras, sistema, agora):
        """Uma sugestão por material que ainda falta, com as melhores estações."""
        if not sistema:
            return []

        faltas = {}
        internos = {}
        for obra in obras:
            for material in obra.materiais:
                if material.faltando <= 0:
                    continue
                faltas[material.nome] = faltas.get(material.nome, 0) + material.faltando
                if material.nome_interno:
                    internos[material.nome] = material.nome_interno

        pad = ardent.pad_necessario(self.nave)
        resultado = []

        for nome in sorted(faltas, key=lambda n: (-faltas[n], n)):
            interno = internos.get(nome, "")
            if not interno:
                resultado.append(
                    SugestaoMaterial(material=nome, faltando=faltas[nome], consultavel=False)
                )
                continue

            estacoes, desatualizado, quando = self._buscar(
                ardent.nome_para_api(interno), sistema, agora, pad
            )
            resultado.append(
                SugestaoMaterial(
                    material=nome,
                    faltando=faltas[nome],
                    estacoes=estacoes,
                    desatualizado=desatualizado,
                    quando=quando,
                )
            )
        return resultado

    def _buscar(self, material, sistema, agora, pad):
        """(estações, desatualizado, quando). Mantém o último resultado bom se a API falhar.

        ``quando`` é a hora do dado devolvido — a do último sucesso quando o
        resultado vem do cache ou de uma falha lembrada, None quando nunca
        houve um sucesso para essa chave.
        """
        chave = (material, sistema)
        entrada = self._cache.get(chave)
        limite = datetime.timedelta(minutes=VALIDADE_CACHE_MINUTOS)
        limite_falha = datetime.timedelta(minutes=VALIDADE_FALHA_MINUTOS)

        # Entradas expiradas de OUTRAS chaves são descartadas: o valor armazenado é a
        # lista bruta da API, que é grande (~235 KB por material/sistema), então deixar
        # lingar para sempre consumiria muita memória no cliente.
        expiradas = [k for k, e in self._cache.items()
                     if k != chave and agora - e.quando >= limite]
        for k in expiradas:
            del self._cache[k]
        falhas_expiradas = [k for k, quando in self._falhas.items()
                            if k != chave and agora - quando >= limite_falha]
        for k in falhas_expiradas:
            del self._falhas[k]

        if entrada is not None and agora - entrada.quando < limite:
            return ardent.melhores(entrada.estacoes, pad, agora), False, entrada.quando

        falha = self._falhas.get(chave)
        if falha is not None and agora - falha < limite_falha:
            # Falha recente e ainda dentro da janela: não reconsulta. Sem
            # isso, um sistema que o Ardent não conhece vira uma requisição a
            # cada ciclo, para sempre.
            if entrada is None:
                return [], True, None
            return ardent.melhores(entrada.estacoes, pad, agora), True, entrada.quando

        cru = self._consultar(sistema, material, self._volume_minimo())
        if cru is None:
            self._falhas[chave] = agora
            if entrada is None:
                return [], True, None
            return ardent.melhores(entrada.estacoes, pad, agora), True, entrada.quando

        self._falhas.pop(chave, None)
        self._cache[chave] = _Entrada(estacoes=cru, quando=agora)
        return ardent.melhores(cru, pad, agora), False, agora
