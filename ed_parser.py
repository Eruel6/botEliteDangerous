"""Leitura do Journal do Elite Dangerous: extração de instalações em construção.

O Journal é um arquivo JSON-lines. Dois eventos interessam:

- ``ColonisationConstructionDepot``: traz ``MarketID``, o progresso e a lista
  ``ResourcesRequired`` com os materiais. Não traz o nome da instalação.
- ``ApproachSettlement``: traz ``MarketID`` e ``Name``.

O ``MarketID`` é a chave exata que liga os dois.
"""

import glob
import json
import os
import re
from dataclasses import dataclass, field

NOME_DESCONHECIDO = "Desconhecida"
# Casa com solo ("Planetary Construction Site:") e com órbita
# ("Orbital Construction Site:", "Space Construction Site:").
MARCA_CONSTRUCAO = "Construction Site:"
PASTA_JOURNAL_PADRAO = os.path.join("~", "Saved Games", "Frontier Developments", "Elite Dangerous")


@dataclass
class Material:
    nome: str
    nome_interno: str
    requerido: int
    fornecido: int

    @property
    def faltando(self):
        return self.requerido - self.fornecido

    @property
    def completo(self):
        return self.fornecido >= self.requerido


@dataclass
class Instalacao:
    market_id: int
    nome: str = NOME_DESCONHECIDO
    materiais: list = field(default_factory=list)
    progresso: float = 0.0
    completa: bool = False
    falhou: bool = False
    sistema: str = ""
    _ordem: int = -1

    @property
    def porcentagem(self):
        """Conclusão em 0-100, pela soma das quantidades de material."""
        total = sum(m.requerido for m in self.materiais)
        if total == 0:
            return 0.0
        return sum(m.fornecido for m in self.materiais) / total * 100


def e_nome_de_construcao(nome):
    return MARCA_CONSTRUCAO in (nome or "")


def _melhor_nome(candidatos, sinais):
    """Melhor nome disponível para uma instalação, do mais explícito ao mais cru.

    O jogo nem sempre reporta o nome completo: um ApproachSettlement pode vir
    como "Sweet Beacon" enquanto o FSS anuncia "Planetary Construction Site:
    Sweet Beacon". E sites orbitais não geram ApproachSettlement nenhum, só
    Docked. Exigir o prefixo em ApproachSettlement fazia essas instalações
    virarem Desconhecida e sumirem das mensagens.
    """
    for nome in candidatos:
        if e_nome_de_construcao(nome):
            return nome
    for nome in candidatos:
        for sinal in sinais:
            if sinal.endswith(f": {nome}"):
                return sinal
    return candidatos[0] if candidatos else NOME_DESCONHECIDO


def _material(bruto):
    return Material(
        nome=bruto.get("Name_Localised", bruto.get("Name", "?")),
        nome_interno=bruto.get("Name", ""),
        requerido=bruto.get("RequiredAmount", 0),
        fornecido=bruto.get("ProvidedAmount", 0),
    )


def registros(caminho_log):
    """Cada linha do Journal como dicionário; linhas inválidas são puladas.

    Público porque o comandante.py precisa do mesmo fluxo — dois parsers do
    mesmo arquivo seria uma divergência esperando para acontecer.
    """
    with open(caminho_log, "r", encoding="utf-8") as f:
        for linha in f:
            try:
                yield json.loads(linha)
            except json.JSONDecodeError:
                continue


def sistema_atual(caminho_log):
    """Sistema do registro mais recente do log que carrega um ``StarSystem``.

    "" se nenhum registro carregar um. Espelha o rastreamento de
    ``sistema_corrente`` feito dentro de ``extrair_instalacoes``: aqui o
    interesse é onde o piloto está agora, não o sistema de nenhuma obra —
    ``comandante.alvo_atual`` já cobre esse outro caso, e é sticky de
    propósito porque serve a um problema diferente.
    """
    sistema = ""
    for registro in registros(caminho_log):
        if isinstance(registro, dict) and registro.get("StarSystem"):
            sistema = registro["StarSystem"]
    return sistema


def extrair_instalacoes(caminho_log):
    """Devolve uma ``Instalacao`` por MarketID, com o estado mais recente do log."""
    por_market = {}
    candidatos = {}
    sinais = set()
    sistema_corrente = ""

    for ordem, registro in enumerate(registros(caminho_log)):
        if not isinstance(registro, dict):
            continue
        evento = registro.get("event")

        # Qualquer evento que carregue StarSystem serve: FSDJump, Location,
        # Docked, SupercruiseExit. Rastrear o corrente cobre a obra planetária,
        # que é aproximada sem pouso e cujo ApproachSettlement não traz sistema.
        if registro.get("StarSystem"):
            sistema_corrente = registro["StarSystem"]

        if evento in ("ApproachSettlement", "Docked"):
            nome = registro.get("Name") or registro.get("StationName")
            if nome:
                vistos = candidatos.setdefault(registro.get("MarketID"), [])
                if nome not in vistos:
                    vistos.append(nome)

        elif evento == "FSSSignalDiscovered":
            sinal = registro.get("SignalName", "")
            if MARCA_CONSTRUCAO in sinal:
                sinais.add(sinal)

        elif evento == "ColonisationConstructionDepot":
            market_id = registro.get("MarketID")
            instalacao = por_market.setdefault(market_id, Instalacao(market_id=market_id))
            instalacao.materiais = [_material(m) for m in registro.get("ResourcesRequired", [])]
            instalacao.progresso = registro.get("ConstructionProgress", 0.0)
            instalacao.completa = registro.get("ConstructionComplete", False)
            instalacao.falhou = registro.get("ConstructionFailed", False)
            instalacao._ordem = ordem
            instalacao.sistema = sistema_corrente

    for market_id, instalacao in por_market.items():
        instalacao.nome = _melhor_nome(candidatos.get(market_id, []), sinais)

    return list(por_market.values())


def sinais_de_construcao(caminho_log):
    """Nomes dos Planetary Construction Sites anunciados por FSSSignalDiscovered."""
    return {
        r["SignalName"]
        for r in registros(caminho_log)
        if isinstance(r, dict)
        and r.get("event") == "FSSSignalDiscovered"
        and MARCA_CONSTRUCAO in r.get("SignalName", "")
    }


def instalacao_de_payload(nome, materiais, market_id=None, sistema=""):
    """Monta uma ``Instalacao`` a partir do JSON recebido pela API."""
    return Instalacao(
        market_id=market_id,
        nome=nome,
        materiais=[_material(m) for m in materiais],
        sistema=sistema,
    )


def ultima_instalacao(caminho_log):
    """A instalação cujo depot foi atualizado por último no log (None se não houver)."""
    instalacoes = extrair_instalacoes(caminho_log)
    if not instalacoes:
        return None
    return max(instalacoes, key=lambda i: i._ordem)


def encontrar_log_mais_recente(pasta=None):
    """Journal modificado mais recentemente na pasta do jogo (None se não houver)."""
    if pasta is None:
        pasta = PASTA_JOURNAL_PADRAO
    arquivos = glob.glob(os.path.join(os.path.expanduser(pasta), "Journal.*.log"))
    if not arquivos:
        return None
    return max(arquivos, key=os.path.getmtime)


LIMITE_LINHA_CREDITO = 300


def formatar_creditos(por_pessoa, limite=LIMITE_LINHA_CREDITO):
    """"entregue: Eruel 1440t · btpopov 720t", cortada no limite."""
    if not por_pessoa:
        return ""

    ordenado = sorted(por_pessoa.items(), key=lambda item: (-item[1], item[0]))
    partes = []
    tamanho = len("entregue: ")
    for quem, total in ordenado:
        pedaco = f"{quem} {total}t"
        adicional = len(pedaco) + (3 if partes else 0)
        if tamanho + adicional > limite:
            break
        partes.append(pedaco)
        tamanho += adicional

    restantes = len(ordenado) - len(partes)
    if restantes:
        partes.append(f"+{restantes}")
    return "entregue: " + " · ".join(partes)


_LINHA_DE_CREDITO = re.compile(r"^-# entregue: (.+)$", re.MULTILINE)
_UM_CREDITO = re.compile(r"^(.+) (\d+)t$")


def creditos_na_mensagem(conteudo):
    """Créditos relidos de uma mensagem já postada. O '+N' final é descartado.

    Não é usada pela reconciliação: reler o total do canal duplicaria, porque o
    cliente reenvia todas as entregas da sessão a cada ciclo. Existe para o
    formato ser testável de ida e volta, e para uma reconciliação futura com
    armazenamento persistente.
    """
    achado = _LINHA_DE_CREDITO.search(conteudo or "")
    if not achado:
        return {}
    creditos = {}
    for pedaco in achado.group(1).split(" · "):
        item = _UM_CREDITO.match(pedaco.strip())
        if item:
            creditos[item.group(1)] = int(item.group(2))
    return creditos


def formatar_mensagem_discord(instalacao, porcentagem=None, rodape=None, creditos=None):
    """Bloco de código para o Discord. ``porcentagem`` e ``rodape`` são opcionais."""
    sufixo = f" `{porcentagem}`" if porcentagem is not None else ""
    linhas = [f"📍 **Materiais para instalação:** `{instalacao.nome}`{sufixo}\n"]
    linhas.append("```")
    linhas.append(f"{'Material':<25} | {'Req.':>5} | {'Fornec.':>7} | {'Faltam':>6}")
    linhas.append("-" * 52)
    for m in instalacao.materiais:
        linhas.append(f"{m.nome:<25} | {m.requerido:>5} | {m.fornecido:>7} | {m.faltando:>6}")
    linhas.append("```")
    if rodape:
        # -# é a marcação de subtexto do Discord: menor e apagado.
        linhas.append(f"-# {rodape}")
    linha_credito = formatar_creditos(creditos or {})
    if linha_credito:
        linhas.append(f"-# {linha_credito}")
    return "\n".join(linhas)


_NOME_NA_MENSAGEM = re.compile(r"^📍 \*\*Materiais para instalação:\*\* `([^`]+)`")


def nome_na_mensagem(conteudo):
    """Nome da instalação a partir de uma mensagem já postada (None se não for uma)."""
    achado = _NOME_NA_MENSAGEM.match(conteudo or "")
    return achado.group(1) if achado else None


_LINHA_DE_MATERIAL = re.compile(r"^(.+?)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+-?\d+$")


def materiais_na_mensagem(conteudo):
    """Materiais relidos de uma mensagem já postada, para reconstruir o estado."""
    materiais = []
    for linha in (conteudo or "").splitlines():
        achado = _LINHA_DE_MATERIAL.match(linha)
        if not achado or achado.group(1) == "Material":
            continue
        nome, requerido, fornecido = achado.groups()
        materiais.append(
            Material(
                nome=nome.strip(),
                nome_interno="",
                requerido=int(requerido),
                fornecido=int(fornecido),
            )
        )
    return materiais


def nave_atual(caminho_log):
    """(nave, capacidade de carga) do último Loadout. ("", 0) se não houver.

    O Loadout é reescrito a cada troca de nave ou de módulo, então o último do
    log é o que vale.
    """
    nave = ""
    capacidade = 0
    for registro in registros(caminho_log):
        if isinstance(registro, dict) and registro.get("event") == "Loadout":
            nave = registro.get("Ship", "") or ""
            capacidade = registro.get("CargoCapacity", 0) or 0
    return nave, capacidade


def formatar_tabela_terminal(instalacao):
    """Tabela de largura dinâmica para stdout, como a do parserMaterials original."""
    cabecalho = ("Material", "Requisitado", "Fornecido", "Faltando")
    largura_nome = max([len(m.nome) for m in instalacao.materiais] + [len(cabecalho[0])])
    larguras = (largura_nome, len(cabecalho[1]), len(cabecalho[2]), len(cabecalho[3]))

    linhas = [f"\n📍 Materiais para instalação: {instalacao.nome}\n"]
    linhas.append(
        f"{cabecalho[0]:<{larguras[0]}} | {cabecalho[1]:>{larguras[1]}} | "
        f"{cabecalho[2]:>{larguras[2]}} | {cabecalho[3]:>{larguras[3]}}"
    )
    linhas.append("-" * (sum(larguras) + 9))
    for m in instalacao.materiais:
        linhas.append(
            f"{m.nome:<{larguras[0]}} | {m.requerido:>{larguras[1]}} | "
            f"{m.fornecido:>{larguras[2]}} | {m.faltando:>{larguras[3]}}"
        )
    return "\n".join(linhas) + "\n"
