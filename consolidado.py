"""Soma, por material, o que falta em todas as obras abertas do esquadrão.

Três funções puras: agregar, formatar e decidir o que fazer com a mensagem.
Nenhuma delas toca banco, Discord ou relógio — quem tem esses é o servidor.
"""

from dataclasses import dataclass

import ed_parser


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


CABECALHO = "🧾 **Consolidado do esquadrão**"
LIMITE_MENSAGEM = 2000
LIMITE_LINHA_OBRAS = 300

LARGURA_MATERIAL = 25
LARGURA_FALTAM = 7
LARGURA_OBRAS = 5


def nome_curto(nome):
    """Nome da obra sem o prefixo de construção, que é igual em todas."""
    posicao = nome.find(ed_parser.MARCA_CONSTRUCAO)
    if posicao == -1:
        return nome
    curto = nome[posicao + len(ed_parser.MARCA_CONSTRUCAO):].strip()
    return curto or nome


def _linha_de_obras(nomes):
    """Nomes separados por '·', cortados no teto, com '+N outras' no fim."""
    curtos = sorted(nome_curto(n) for n in nomes)
    escolhidos = []
    tamanho = 0
    for curto in curtos:
        adicional = len(curto) + (3 if escolhidos else 0)
        if tamanho + adicional > LIMITE_LINHA_OBRAS:
            break
        escolhidos.append(curto)
        tamanho += adicional

    linha = " · ".join(escolhidos)
    restantes = len(curtos) - len(escolhidos)
    if not restantes:
        return linha
    return f"{linha} · +{restantes} outras" if linha else f"+{restantes} outras"


def _resumo_do_corte(linhas):
    if not linhas:
        return ""
    total = sum(l.faltando for l in linhas)
    return f"+{len(linhas)} materiais menores ({total} no total)"


def formatar_consolidado(retrato, quando):
    """Mensagem do Discord, cortada para caber em LIMITE_MENSAGEM.

    A prioridade do orçamento é: cabeçalho e rodapé nunca saem, depois a linha
    de nomes das obras, depois os materiais na ordem decrescente, e por último
    a linha de resumo do que foi cortado.
    """
    quantas = len(retrato.obras)
    topo = (
        f"{'Material':<{LARGURA_MATERIAL}} | {'Faltam':>{LARGURA_FALTAM}} | "
        f"{'Obras':>{LARGURA_OBRAS}}"
    )

    fixo = [f"{CABECALHO} `{quantas} obra{'s' if quantas != 1 else ''}`"]
    linha_obras = _linha_de_obras(retrato.obras)
    if linha_obras:
        fixo.append(linha_obras)
    fixo += ["", "```", topo, "-" * len(topo)]
    fim = ["```", f"-# atualizado às {quando.strftime('%H:%M')} UTC"]

    def tamanho(corpo, resumo):
        partes = fixo + corpo + ([resumo] if resumo else []) + fim
        return len("\n".join(partes))

    corpo = []
    for indice, linha in enumerate(retrato.linhas):
        candidata = (
            f"{linha.material:<{LARGURA_MATERIAL}} | {linha.faltando:>{LARGURA_FALTAM}} | "
            f"{linha.obras:>{LARGURA_OBRAS}}"
        )
        if tamanho(corpo + [candidata], _resumo_do_corte(retrato.linhas[indice + 1:])) > LIMITE_MENSAGEM:
            break
        corpo.append(candidata)

    resumo = _resumo_do_corte(retrato.linhas[len(corpo):])
    return "\n".join(fixo + corpo + ([resumo] if resumo else []) + fim)
