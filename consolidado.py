"""Soma, por material, o que falta em todas as obras abertas do esquadrão.

Três funções puras: agregar, formatar e decidir o que fazer com a mensagem.
Nenhuma delas toca banco, Discord ou relógio — quem tem esses é o servidor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LinhaConsolidada:
    material: str
    faltando: int
    obras: int


@dataclass(frozen=True)
class Retrato:
    """``linhas`` é tupla e ``obras`` é frozenset para o retrato ser comparável
    com ``==``: é assim que os gatilhos detectam que nada mudou. O frozenset
    ainda garante que a comparação não dependa da ordem em que as obras saíram
    do banco. Quem ordena para exibição é o formatador."""

    linhas: tuple
    obras: frozenset


def consolidar(instalacoes):
    """Retrato do que falta, somando todas as obras."""
    totais = {}
    obras = set()

    for instalacao in instalacoes:
        contribuiu = False
        for material in instalacao.materiais:
            faltando = max(0, material.faltando)
            if faltando == 0:
                continue
            acumulado = totais.setdefault(material.nome, [0, 0])
            acumulado[0] += faltando
            acumulado[1] += 1
            contribuiu = True
        if contribuiu:
            obras.add(instalacao.nome)

    linhas = tuple(
        LinhaConsolidada(material=nome, faltando=faltando, obras=quantas)
        for nome, (faltando, quantas) in sorted(
            totais.items(), key=lambda item: (-item[1][0], item[0])
        )
    )
    return Retrato(linhas=linhas, obras=frozenset(obras))
