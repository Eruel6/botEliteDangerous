# Aba de exploração e exobiologia no painel

Data: 2026-11-14
Status: aguardando revisão

## Intenção

O Arthur está fazendo exobiologia e quer **acompanhar o que já fez**, não
planejar a próxima parada. Uma aba nova no painel local do cliente
(`painel.html`) mostra:

1. As amostras biológicas coletadas, com valor e se o bônus de primeira
   descoberta é provável.
2. Os sistemas e planetas em que ele foi o primeiro a descobrir, a mapear
   (sonda) e a pousar (pisar).
3. Médias de valor do que foi coletado.
4. Tudo separado em **a bordo** (ainda não vendido, perde-se se morrer) e
   **vendido**.

É só para ele: nada vai para o servidor do esquadrão nem para o Discord.

## Objetivos, não-objetivos, anti-objetivos

**Objetivos**
- Histórico de toda a carreira presente na pasta de journals, não só da sessão.
- Atualizar ao vivo enquanto ele joga (mesma cadência do painel atual).
- Valor estimado de cada amostra a bordo; valor real das vendidas.

**Não-objetivos**
- Sugerir rota, planeta ou espécie a buscar.
- Enviar qualquer coisa ao servidor (`servidor.py`) ou ao Discord.
- Buscar preços na internet em tempo de execução.
- Ler `Status.json` ou o `.binds`.

**Anti-objetivos** (falharia mesmo "funcionando")
- Afirmar que o bônus está **garantido**. Ele só é certo depois da venda; antes
  disso é "provável" (ver Bônus).
- Um erro na leitura de exploração derrubar ou atrasar o relato de colonização.
  Os dois são independentes.
- Exigir `config.txt` válido: a aba não usa token nem servidor, então funciona
  mesmo com a config inválida.

## O que o jogo entrega

Confirmado no journal real `journals/Journal.2026-11-14T094935.01.log.txt`
(Portuguese/BR, Odyssey 4.4.2.1):

| Evento | Campos usados |
|---|---|
| `ScanOrganic` | `ScanType` (`Log`/`Sample`/`Analyse`), `Genus`, `Species`, `Species_Localised`, `Variant_Localised`, `WasLogged`, `SystemAddress`, `Body` (é o **BodyID**, um inteiro) |
| `Scan` | `BodyName`, `BodyID`, `SystemAddress`, `StarSystem`, `WasDiscovered`, `WasMapped`, `WasFootfalled`, `Landable`, `DistanceFromArrivalLS` |
| `SAAScanComplete` | `BodyName`, `BodyID`, `SystemAddress`, `ProbesUsed`, `EfficiencyTarget` |
| `Disembark` | `OnPlanet`, `SystemAddress`, `BodyID`, `Body` |
| `Statistics` | bloco `Exobiology` (totais da carreira) |

Exemplo real: Bacterium Acies (Água-marinha) em Plio Eurl IX-Z b14-0 B 1 —
`Log` 13:31:44, `Sample` 13:35:07, `Sample` 13:42:09, `Analyse` 13:42:14. O
`Scan` desse corpo veio com `WasDiscovered`, `WasMapped` e `WasFootfalled`
todos `false`.

**Ainda não visto num journal real** (formato documentado pela comunidade, a
confirmar na primeira ocorrência):
- `SellOrganicData`: `MarketID`, `BioData[]` com `Genus`, `Species`,
  `Species_Localised`, `Variant`, `Value`, `Bonus`.
- `SellExplorationData`: `Systems[]` (nomes), `Discovered[]`, `BaseValue`,
  `Bonus`, `TotalEarnings`.
- `MultiSellExplorationData`: `Discovered[]` com `SystemName` e `NumBodies`,
  `BaseValue`, `Bonus`, `TotalEarnings`.
- `Died`: sem campos relevantes; o evento em si basta.

Os testes desses quatro usam fixtures sintéticas e devem ser revistos quando
aparecer um real.

## Abordagens consideradas

- **A. Ler tudo ao abrir, depois só o journal atual (escolhida).** Ao subir, o
  cliente lê todos os `Journal.*.log` da pasta em ordem cronológica e guarda o
  resultado em memória. Depois, a cada ciclo, lê só as linhas novas do journal
  atual. Simples, sem arquivo extra; custa alguns segundos na abertura.
- **B. Igual, com resumo salvo em disco.** Abre mais rápido, mas exige manter um
  cache coerente com a regra de cálculo. Fica para depois, se A ficar lenta.
- **C. Só a sessão atual.** Descartada: vendas e mortes de sessões antigas
  sumiriam, e "a bordo" sairia errado.

O Arthur escolheu A.

**Preços:** tabela salva no projeto (escolha do Claude, aceita na conversa), e
não buscada na hora: os valores quase não mudam e a aba não deve depender de
site de terceiro no ar.

## Desenho

### Peças

| Arquivo | Papel |
|---|---|
| `exploracao.py` (novo) | Lógica pura: consome eventos e mantém o histórico. Sem I/O de rede. |
| `precos_vista.json` (novo) | Preço base por espécie. |
| `scripts/atualizar_precos_vista.py` (novo) | Baixa `https://ed-dsn.net/en/vista-genomics-values/`, lê a tabela HTML (`table#tablepress-171`, colunas "espécie" e "NN NNN NNN Cr") e reescreve `precos_vista.json`. Rodado à mão. |
| `leitor_exploracao.py` (novo) | Thread própria: carga inicial + leitura incremental; publica no estado. |
| `estado.py` | Ganha `registrar_exploracao(dicionario)` e o campo no snapshot da aba. |
| `painel.py` | Nova rota `GET /exploracao.json`. |
| `painel.html` | Duas abas: "Colonização" (o conteúdo atual, intacto) e "Exploração". |
| `cliente.py` | Sobe a thread de exploração logo após o painel, **antes** de carregar a config, para funcionar mesmo com config inválida. |

### `exploracao.py`

Uma classe `Historico` com `consumir(evento: dict)` e `resumo() -> dict`.
A carga inicial e a incremental chamam o mesmo `consumir`, então não há dois
caminhos de cálculo.

Estado interno:
- **corpos**: chave `(SystemAddress, BodyID)` → nome, sistema, flags
  `WasDiscovered/WasMapped/WasFootfalled`, se você mapeou (`SAAScanComplete`),
  se você pisou (`Disembark` com `OnPlanet: true`).
- **sistemas**: chave `SystemAddress` → nome; "primeiro a descobrir o sistema"
  = a estrela principal (`DistanceFromArrivalLS == 0`) veio com
  `WasDiscovered: false`.
- **amostras a bordo**: cada `Analyse` vira uma amostra (espécie, variante,
  corpo, horário, preço base, bônus provável).
- **amostras vendidas**: vindas de `SellOrganicData`, com `Value` e `Bonus` reais.
- **amostras perdidas**: as que estavam a bordo num `Died`.
- **exploração a bordo / vendida**: sistemas com corpos escaneados; saem de "a
  bordo" quando aparecem num `SellExplorationData`/`MultiSellExplorationData`
  (casando pelo nome do sistema); somem num `Died` (marcados como perdidos).
- **último `Statistics.Exobiology`**: totais da carreira, mostrados como
  referência.

Regras:
- Só `ScanType == "Analyse"` gera amostra. `Log`/`Sample` são ignorados (poderiam
  virar "em andamento" no futuro; fora do escopo).
- **Venda casa com a bordo por espécie (`Species`, o id interno), na ordem de
  coleta (FIFO).** O `SellOrganicData` não diz o planeta. Item vendido sem par a
  bordo (coleta anterior ao journal mais antigo) entra em "vendido" sem planeta.
- **Pisar** não vai para "a bordo": é registrado na hora pelo jogo (premissa; ver
  Pendências).

### Bônus

- **Provável** quando o corpo da amostra tem `WasFootfalled: false` no `Scan`.
  Valor mostrado: base × 5 (bônus de 4× o base, mais o próprio base).
- **Desconhecido** quando não há `Scan` do corpo no histórico.
- **Improvável** quando `WasFootfalled: true`.
- Depois da venda, vale o `Bonus` real do `SellOrganicData`, e a aba mostra se a
  previsão acertou. Isso é o que confirma ou corrige a regra ×5.

### Preços (`precos_vista.json`)

Formato: `{"fonte": url, "atualizado_em": data, "especies": {"Bacterium Acies": 1000000, ...}}`.

Casamento com o journal: pelo `Species_Localised` normalizado (sem acento,
minúsculas). Os nomes em latim são iguais em português e inglês. As poucas
espécies com nome traduzido (Anemone, Brain Tree, Bark Mounds, Sinuous Tubers,
Crystalline Shards, Amphora Plant) ganham um mapa de apelidos à mão no próprio
JSON (`"apelidos": {"<nome em pt>": "<nome do site>"}`), preenchido quando
aparecerem num journal real. Espécie sem preço aparece com "sem preço" e não
entra nas médias de valor.

### Leitura (`leitor_exploracao.py`)

- Pasta: a mesma de `ed_parser.encontrar_log_mais_recente` (reaproveitar a
  constante/função de pasta).
- Carga inicial: todos os `Journal.*.log` ordenados pelo nome (o nome contém a
  data/hora), cada linha passada a `Historico.consumir`. Linha inválida é
  pulada, como em `ed_parser.registros`.
- Incremental: guarda `(caminho, posição em bytes)` do journal atual; a cada
  ciclo (60 s, mesmo `INTERVALO_CHECAGEM`) lê só o que foi acrescentado. Se surgir
  um journal mais novo, termina o atual e passa para o novo.
- Uma linha incompleta no fim (o jogo ainda escrevendo) não é consumida: a
  posição só avança até o último `\n`.
- Erro vira `estado_cliente.registrar_erro("exploração: ...")` e a thread
  continua.

### Painel

`/exploracao.json` devolve o `resumo()` mais `carregando: bool`.

Esboço da aba:

```
[ Colonização ]  [ Exploração ]

A BORDO  (perde-se se morrer)
  Amostras: 3   Base: 4,6 mi   Com bônus provável: 21,4 mi
  Espécie                     Planeta                    Base     Bônus
  Bacterium Acies · Água-m.   Plio Eurl IX-Z b14-0 B 1   1,0 mi   provável
  ...
  Dados de exploração: 2 sistemas, 33 corpos

VENDIDO
  Amostras: 27   Total: 439,5 mi   Média por amostra: 16,3 mi
  ...

MÉDIAS (coletado)
  Por amostra · Por planeta com coleta · Por sessão (journal)

PRIMEIRO A...
  Descobrir sistema: N   Descobrir corpo: N   Mapear: N   Pisar: N
  Sistema / Corpo              Descobriu  Mapeou  Pisou
  Plio Eurl IX-Z b14-0 B 1     ✓          ✓       ✓

CARREIRA (dados do próprio jogo, evento Statistics)
  27 amostras · 439,5 mi · 25 primeiras descobertas
```

Mesmo estilo visual do painel atual (mesmo CSS, mesma consulta a cada 5 s).

### Testes

- `tests/fixtures/journal_exobio.log`: recorte do journal real de 2026-11-14
  (Scan, SAAScanComplete, Disembark, as quatro ScanOrganic, Statistics).
- Fixtures sintéticas para `SellOrganicData`, `SellExplorationData`,
  `MultiSellExplorationData` e `Died`.
- Casos: amostra só no `Analyse`; bônus provável/desconhecido/improvável; venda
  FIFO; venda sem par; morte zera a bordo; incremental não relê nem perde linha;
  linha parcial no fim; espécie sem preço; parser do HTML do site (com uma cópia
  salva da página em fixture).

## Pendências (confirmar quando aparecerem num journal real)

1. Formato de `SellOrganicData` e se o bônus é exatamente 4× o base.
2. Se `WasFootfalled: false` basta para o bônus, ou se `WasLogged` também conta.
3. Se a primeira pisada é registrada na hora ou só na venda (e portanto se
   também se perde numa morte).
4. Nomes traduzidos das espécies sem latim, para o mapa de apelidos.
5. Tempo de carga inicial com a pasta inteira do Arthur. Se passar de ~10 s,
   reavaliar a abordagem B.
