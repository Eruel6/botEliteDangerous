# Onde comprar o que falta

Data: 2026-09-05
Status: aguardando revisão
Subsistema: 3 de 3
Depende de: nada. Roda inteiro no cliente e não toca o servidor.

## Problema

O consolidado diz o que falta. O subsistema 2 diz o que já está a caminho.
Nenhum dos dois diz **onde comprar** — e essa é a pergunta que o piloto faz
parado numa estação, decidindo o que fazer com o porão vazio.

Hoje a resposta vem de sair do jogo, abrir o Inara ou o Spansh no navegador,
consultar material por material e voltar. Com uma dúzia de materiais faltando,
ninguém faz isso.

## Por que isso não vai para o Discord

A consulta é **"perto de mim"**. O que está perto do Arthur não está perto do
btpopov. Uma mensagem no canal compartilhado responderia a pergunta errada para
metade do esquadrão, e teria que ser relativa ao sistema da obra — que é o
destino, não a origem da compra.

Consequência boa: este subsistema roda inteiro no cliente. **Zero mudança no
servidor**, nenhuma tabela nova, nenhum endpoint novo, e nenhum problema de
cache com o disco efêmero do Render.

## A API

[Ardent Insight](https://api.ardent-insight.com/v2/), REST público, sem chave,
sem rate limit declarado, stack open source.

```
GET /v2/system/name/{sistema}/commodity/name/{commodity}/nearby/exports
    ?maxDistance=…&minVolume=…
```

Comportamento confirmado por chamadas reais em 2026-09-05:

| Caso | Resposta |
|---|---|
| consulta válida | `200` com lista de estações |
| commodity desconhecida | `200` com `[]` — **não é erro** |
| sistema desconhecido | `404` com `{"error":"Not Found","message":"System not found"}` |

Campos por estação: `stationName`, `stationType`, `systemName`, `distance` (ly
da origem), `distanceToArrival` (Ls), `maxLandingPadSize`, `stock`, `buyPrice`,
`updatedAt`, `marketId`.

**O volume da resposta é o problema real.** `Sol` / `aluminium` com
`maxDistance=50&minVolume=5000` devolveu **589 estações**. Sem cuidado, isso é
um quarto de megabyte por material, por ciclo.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Onde roda | Cliente, exibido no painel | A consulta é relativa a quem pergunta. |
| Nome do material | `nome_interno` convertido | A API quer inglês; o jogo do Arthur está em português. |
| Fleet Carriers | **Ficam**, marcados com `🛸` | Escolha do Arthur. Os outros filtros já derrubam a maior parte dos ruins. |
| Filtro de pad | Tabela nave → pad, padrão "não filtra" | Filtrar errado esconde estação boa; não filtrar só deixa passar ruim. |
| Filtro de validade | 30 dias no `updatedAt` | A mesma consulta trouxe dados de junho e de agosto misturados. |
| Filtro de estoque | `minVolume` na própria API | Empurrar para o servidor deles reduz a resposta em vez de baixar e descartar. |
| Raio | 50 ly por padrão | Equilíbrio entre achar algo e não baixar meio universo. |
| Ritmo | Cache em memória, 15 min por (material, sistema) | O preço não muda em 60 s, e o ciclo do cliente é de 60 s. |
| Quantos mostrar | 3 estações por material | O painel é um painel, não uma planilha. |

## O nome do material

A API quer `aluminium`. O Journal dá `Name: "$Aluminium_name;"` e
`Name_Localised: "Alumínio"`.

```python
def nome_para_api(nome_interno):
    return nome_interno.strip("$").removesuffix("_name;").lower()
```

**Obra vinda da reconciliação do canal não é consultável.** A mensagem do
Discord só carrega o nome localizado, então `nome_interno` vem vazio. Essas
obras aparecem no painel com a nota "sem dados de compra até alguém reportar de
novo".

Não haverá tabela de tradução do português de volta para o inglês: seria dado
mantido à mão, por idioma, para resolver um caso que se resolve sozinho no
próximo relato de quem estiver com o jogo aberto.

## Os filtros

| Filtro | Regra | Onde |
|---|---|---|
| Estoque | `stock >= 25%` do `CargoCapacity` | na API, via `minVolume` |
| Raio | 50 ly | na API, via `maxDistance` |
| Pad | `maxLandingPadSize >= pad_necessario(nave)` | no cliente |
| Validade | `updatedAt` nos últimos 30 dias | no cliente |

O pad usa uma tabela estática nave → pad exigido, com **padrão 1 (não filtra)**
para nave desconhecida. `type9 = 3` entra confirmado pelo `Loadout` real do
Arthur; o resto é dado a conferir na implementação, do mesmo jeito que o formato
do `Cargo.json` no subsistema 2.

Nave pequena e média não precisa de filtro nenhum — ela pousa em qualquer lugar.
O filtro só ganha alguma coisa para quem voa nave de pad grande, que é
exatamente o caso de quem carrega material de colonização.

## O que o painel mostra

Uma seção nova, uma linha por material faltante e até três estações abaixo:

```
Alumínio      falta 24 500        4 estações
   Nagasaki Terminal     Wregoe QI-M b48-6     98 ly    2 100 Ls    10 039 t   127 cr
   🛸 K3W-76W            Wregoe JU-E c25-18    65 ly        9 Ls     8 200 t   142 cr
```

Ordenado por `distance` e, em empate, por `buyPrice`. `🛸` marca Fleet Carrier.

Material sem nenhuma estação após os filtros aparece com "nada dentro de 50 ly".
Material de obra reconciliada aparece com a nota de `nome_interno` vazio.

## Cache e ritmo

Cache em memória, chave `(material, sistema)`, validade de 15 minutos. A consulta
dispara quando o sistema corrente muda ou quando a entrada vence. Na prática:
uma rajada ao chegar num sistema novo, silêncio depois.

O cache morre junto com o processo do cliente, e isso está certo — ele existe
para não maltratar a API dentro de uma sessão, não para persistir nada.

## Erros

Nada aqui pode derrubar o ciclo do monitor, que é o que mantém o relato das
obras funcionando.

| Situação | Comportamento |
|---|---|
| Timeout ou falha de rede | Mantém o último resultado bom, com a hora dele |
| `404` (sistema desconhecido) | Marca o material como não consultável neste sistema |
| `[]` | "nada dentro de 50 ly" — é resposta, não erro |
| JSON inesperado | Trata como lista vazia e registra um erro no painel |

## Testes

- conversão de nome, incluindo `nome_interno` vazio e sufixo ausente;
- cada filtro isolado, e os quatro combinados;
- ordenação por distância com desempate por preço, e o corte em três;
- Fleet Carrier sobrevive aos filtros e sai marcado;
- cache devolve sem chamar a API dentro dos 15 min;
- cache é ignorado quando o sistema muda;
- timeout, `404`, `[]` e JSON inválido, cada um com seu comportamento;
- o painel renderiza a seção vazia, a seção com nota de obra reconciliada, e a seção cheia;
- a consulta não roda para material que nenhuma obra precisa.

## Fora de escopo

- Qualquer mudança no servidor ou no Discord.
- Sugestão de rota com várias paradas. O painel diz onde comprar cada coisa; a
  rota é do piloto.
- Onde **vender** (o `/nearby/imports` da API existe e não é usado).
- Cache em disco.
- Tradução de nome localizado para inglês.

## Riscos

**A tabela nave → pad é dado que não verifiquei.** Só o `type9` está confirmado,
pelo Loadout real. O padrão "não filtra" torna um erro de tabela inofensivo:
aparece estação a mais, nunca de menos.

**O volume da resposta.** 589 estações numa consulta real. `minVolume` e
`maxDistance` cortam antes de baixar, e o cache evita repetir, mas em conexão
ruim uma rajada de doze materiais ao chegar num sistema novo é perceptível. O
timeout de 30 s já existente no cliente cobre o caso; o sintoma seria a seção do
painel demorando a preencher, não o cliente travando.

**Dependência de terceiro sem contrato.** O Ardent é gratuito, sem chave e sem
SLA. Se sair do ar, esta seção do painel para e nada mais é afetado — o relato
das obras, o consolidado e a carga continuam. Foi por isso que a consulta ficou
isolada no cliente e fora do caminho do servidor.

**Dado da comunidade envelhece.** `updatedAt` de três meses apareceu na consulta
real. O filtro de 30 dias reduz, não elimina: estoque some entre a consulta e a
chegada. A seção informa, não promete.
