# exploracao.py
"""Histórico de exploração lido do journal: primeiras descobertas e amostras de exobiologia."""

import copy

from precos_vista import Precos

BONUS_PRIMEIRO_REGISTRO = 5


class Historico:
    def __init__(self, precos: Precos):
        self._precos = precos
        self._sistemas = {}          # SystemAddress -> nome
        self._scans = {}             # (SystemAddress, BodyID) -> dados do primeiro Scan
        self._mapeados = set()       # chaves de corpo com SAAScanComplete
        self._pisados = set()        # chaves de corpo com Disembark em planeta
        self._sistemas_descobertos = set()   # SystemAddress
        self._sistemas_com_chegada = set()   # SystemAddress já avaliados por DistanceFromArrivalLS == 0
        self._amostras = []
        # exploração a bordo: nome do sistema -> chaves de corpos escaneados
        self._exploracao = {}
        self._carreira = None
        self._vendidas = []
        self._exploracao_vendida = 0
        self._perdido = {"amostras": 0, "sistemas": 0}

    def consumir(self, evento: dict, sessao: str) -> None:
        tratador = getattr(self, "_ao_" + str(evento.get("event")), None)
        if tratador:
            tratador(evento, sessao)

    def _ao_FSDJump(self, ev, sessao):
        self._lembrar_sistema(ev)

    _ao_Location = _ao_FSDJump

    def _lembrar_sistema(self, ev):
        if ev.get("SystemAddress") is not None and ev.get("StarSystem"):
            self._sistemas[ev["SystemAddress"]] = ev["StarSystem"]

    def _ao_Scan(self, ev, sessao):
        if "BodyID" not in ev or "SystemAddress" not in ev:
            return
        self._lembrar_sistema(ev)
        sa = ev["SystemAddress"]
        chave = (sa, ev["BodyID"])
        if chave not in self._scans:
            self._scans[chave] = {
                "nome": ev.get("BodyName") or f"corpo {ev['BodyID']}",
                "sa": sa,
                "descoberto": bool(ev.get("WasDiscovered")),
                "mapeado": bool(ev.get("WasMapped")),
                "pisado": bool(ev.get("WasFootfalled")),
            }
        if ev.get("DistanceFromArrivalLS") == 0 and sa not in self._sistemas_com_chegada:
            self._sistemas_com_chegada.add(sa)
            if not ev.get("WasDiscovered"):
                self._sistemas_descobertos.add(sa)
        nome_sistema = self._sistemas.get(sa, f"sistema {sa}")
        self._exploracao.setdefault(nome_sistema, set()).add(chave)

    def _ao_SAAScanComplete(self, ev, sessao):
        self._mapeados.add((ev.get("SystemAddress"), ev.get("BodyID")))

    def _ao_Disembark(self, ev, sessao):
        if ev.get("OnPlanet"):
            self._pisados.add((ev.get("SystemAddress"), ev.get("BodyID")))

    def _ao_Statistics(self, ev, sessao):
        self._carreira = ev.get("Exobiology")

    def _ao_ScanOrganic(self, ev, sessao):
        if ev.get("ScanType") != "Analyse":
            return
        sa = ev.get("SystemAddress")
        corpo_id = ev.get("Body")
        scan = self._scans.get((sa, corpo_id))
        especie = ev.get("Species_Localised") or ev.get("Species") or ""
        preco = self._precos.preco(especie)
        if scan is None:
            bonus = "desconhecido"
        else:
            bonus = "improvavel" if scan["pisado"] else "provavel"
        if preco is None:
            valor = None
        elif bonus == "provavel":
            valor = preco * BONUS_PRIMEIRO_REGISTRO
        else:
            valor = preco
        self._amostras.append({
            "especie": especie,
            "especie_id": ev.get("Species", ""),
            "variante": ev.get("Variant_Localised") or ev.get("Variant") or "",
            "corpo": scan["nome"] if scan else f"corpo {corpo_id}",
            "sistema": self._sistemas.get(sa, f"sistema {sa}"),
            "quando": ev.get("timestamp", ""),
            "preco_base": preco,
            "bonus": bonus,
            "valor_estimado": valor,
            "sessao": sessao,
        })

    def _ao_SellOrganicData(self, ev, sessao):
        for item in ev.get("BioData") or []:
            self._vender(item, ev.get("timestamp", ""))

    def _vender(self, item, quando):
        bonus_pago = item.get("Bonus") or 0
        especie_id = item.get("Species")
        par = None
        for i, a in enumerate(self._amostras):   # a lista está em ordem cronológica
            if a["especie_id"] == especie_id:
                par = self._amostras.pop(i)
                break
        previsao = par["bonus"] if par else None
        acertou = None
        if previsao is not None and previsao != "desconhecido":
            acertou = (bonus_pago > 0) == (previsao == "provavel")
        self._vendidas.append({
            "especie": par["especie"] if par else (item.get("Species_Localised") or ""),
            "variante": par["variante"] if par else (item.get("Variant_Localised") or ""),
            "corpo": par["corpo"] if par else None,
            "sistema": par["sistema"] if par else None,
            "quando": quando,
            "valor": (item.get("Value") or 0) + bonus_pago,
            "bonus_pago": bonus_pago,
            "previsao": previsao,
            "acertou": acertou,
            "sessao": par["sessao"] if par else None,
        })

    def _ao_SellExplorationData(self, ev, sessao):
        self._exploracao_vendida += ev.get("TotalEarnings") or 0
        for nome in ev.get("Systems") or []:
            self._exploracao.pop(nome, None)

    def _ao_MultiSellExplorationData(self, ev, sessao):
        self._exploracao_vendida += ev.get("TotalEarnings") or 0
        for d in ev.get("Discovered") or []:
            self._exploracao.pop(d.get("SystemName"), None)

    def _ao_Died(self, ev, sessao):
        self._perdido["amostras"] += len(self._amostras)
        self._perdido["sistemas"] += len(self._exploracao)
        self._amostras = []
        self._exploracao = {}

    def resumo(self) -> dict:
        return copy.deepcopy({
            "a_bordo": self._a_bordo(),
            "vendido": {"amostras": self._vendidas,
                        "total": sum(v["valor"] for v in self._vendidas),
                        "exploracao_total": self._exploracao_vendida},
            "perdido": self._perdido,
            "medias": self._medias(),
            "primeiros": self._primeiros(),
            "carreira": self._carreira,
        })

    def _medias(self):
        # (valor, corpo, sessao) de cada amostra a bordo com preço e de cada vendida
        itens = [(a["valor_estimado"], (a["sistema"], a["corpo"]), a["sessao"])
                 for a in self._amostras if a["valor_estimado"] is not None]
        itens += [(v["valor"], (v["sistema"], v["corpo"]) if v["corpo"] else None, v["sessao"])
                  for v in self._vendidas]

        def media(pares):
            pares = list(pares)
            grupos = {g for _, g in pares}
            return round(sum(v for v, _ in pares) / len(grupos)) if pares else None

        return {
            "por_amostra": round(sum(i[0] for i in itens) / len(itens)) if itens else None,
            "por_planeta": media((v, c) for v, c, _ in itens if c is not None),
            "por_sessao": media((v, s) for v, _, s in itens if s is not None),
        }

    def _a_bordo(self):
        return {
            "amostras": list(self._amostras),
            "total_base": sum(a["preco_base"] or 0 for a in self._amostras),
            "total_com_bonus": sum(a["valor_estimado"] or 0 for a in self._amostras),
            "sistemas_exploracao": len(self._exploracao),
            "corpos_exploracao": sum(len(c) for c in self._exploracao.values()),
        }

    def _primeiros(self):
        corpos = []
        for chave, s in self._scans.items():
            descobriu = not s["descoberto"]
            mapeou = chave in self._mapeados and not s["mapeado"]
            pisou = chave in self._pisados and not s["pisado"]
            if descobriu or mapeou or pisou:
                corpos.append({
                    "corpo": s["nome"],
                    "sistema": self._sistemas.get(s["sa"], f"sistema {s['sa']}"),
                    "descobriu": descobriu, "mapeou": mapeou, "pisou": pisou,
                })
        return {
            "sistemas_descobertos": len(self._sistemas_descobertos),
            "corpos_descobertos": sum(c["descobriu"] for c in corpos),
            "mapeados": sum(c["mapeou"] for c in corpos),
            "pisados": sum(c["pisou"] for c in corpos),
            "corpos": corpos,
        }
