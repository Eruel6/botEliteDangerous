"""Distribui o porão de um comandante entre as obras que ainda precisam do material.

Função pura, sem banco e sem Discord. A regra é do Arthur: tudo vai para a
última obra visitada, o excedente transborda para as outras do mesmo sistema, e
o que sobrar é descartado.
"""


def atribuir(carga, obras_abertas, alvo_market_id, sistema):
    """{market_id: {material: quantidade}} com a carga distribuída."""
    faltas = {}
    sistemas = {}
    for obra in obras_abertas:
        # market_id None vem da reconciliação do canal; duas dessas colidiriam
        # na chave e uma comeria a atribuição da outra.
        if obra.market_id is None:
            continue
        faltas[obra.market_id] = {
            m.nome: m.faltando for m in obra.materiais if m.faltando > 0
        }
        sistemas[obra.market_id] = obra.sistema

    resultado = {}

    def alocar(market_id, material, quantidade):
        cabe = min(quantidade, faltas.get(market_id, {}).get(material, 0))
        if cabe <= 0:
            return 0
        por_obra = resultado.setdefault(market_id, {})
        por_obra[material] = por_obra.get(material, 0) + cabe
        faltas[market_id][material] -= cabe
        return cabe

    for material, quantidade in carga.items():
        restante = quantidade
        if alvo_market_id is not None:
            restante -= alocar(alvo_market_id, material, restante)
        if restante <= 0:
            continue

        outras = [
            market_id
            for market_id, sist in sistemas.items()
            if market_id != alvo_market_id and sist and sist == sistema
        ]
        outras.sort(key=lambda mid: (-faltas.get(mid, {}).get(material, 0), mid))

        for market_id in outras:
            if restante <= 0:
                break
            restante -= alocar(market_id, material, restante)

    return resultado
