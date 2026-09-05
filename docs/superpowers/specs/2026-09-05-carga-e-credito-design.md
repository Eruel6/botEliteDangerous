# Carga a caminho e crédito de entrega

Data: 2026-09-05
Status: aguardando revisão
Subsistema: 2 de 3
Depende de: `2026-09-05-consolidado-esquadrao-design.md` implementado (a coluna
"A caminho" altera `consolidado.py`)

## Problema

O consolidado responde "o que falta". Ele não responde duas perguntas que vêm
logo depois:

1. **"Alguém já está trazendo isso?"** Dois pilotos olham a mesma lista, veem
   24500 de Steel faltando e saem os dois com o porão cheio de Steel. O segundo
   descobre na chegada que a obra já foi suprida.
2. **"Quem está puxando esta obra?"** Não há registro de quem entregou o quê. O
   rodapé diz quem *reportou* por último, que é outra coisa.

Os dois dados já existem no Journal de quem joga. Falta levá-los ao servidor.

## O que o jogo entrega de graça

Confirmado nos Journals reais do Arthur (`journals/`, sessão de 2025-05-20):

| Evento / arquivo | Ocorrências | Traz |
|---|---|---|
| `ColonisationContribution` | 25 | `MarketID` + `Contributions[]` com `Name_Localised` e `Amount` |
| `MarketBuy` | 62 | `MarketID`, `Type_Localised`, `Count`, `BuyPrice` |
| `Docked` | 50 | `MarketID`, `StationName`, `StarSystem` |
| `Cargo` (evento) | 94 | **só `Count`** — `Inventory` vem vazio em 94 de 94 |
| `Cargo.json` | — | o inventário detalhado, sobrescrito a cada mudança |

A entrega não precisa ser inferida: `ColonisationContribution` é o registro
exato do que foi entregue e para qual obra.

**Premissa a confirmar antes de implementar:** o formato do `Cargo.json`. Não
há uma cópia em `journals/` (só os `.log`). O plano assume o formato
documentado — mesma forma do evento `Cargo`, com `Inventory` preenchido:
`Name`, `Name_Localised`, `Count`, `Stolen`. Conferir com um arquivo real da
máquina do jogo antes da Task de parsing.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Fonte do que está no porão | `Cargo.json`, o retrato atual | Autocorrige: vendeu, ejetou ou entregou, o ciclo seguinte já mostra menos. A razão `MarketBuy` menos entregas acumularia erro de venda, mineração e carga de missão. |
| Transporte | Endpoint novo `POST /comandante` | É estado por **pessoa**, não por obra. O `/logdata` é chamado uma vez por obra alterada; este, uma vez por ciclo. |
| Filtro do que conta | No servidor | Só ele sabe o que as obras do esquadrão precisam. O cliente manda a carga inteira. |
| Reenvio de entregas | O cliente reenvia tudo; o servidor deduplica | O cliente relê o Journal inteiro a cada ciclo. Dedup por chave natural sobrevive a restart do Render sem estado no cliente. |
| Atribuição da carga | À obra do alvo, transbordando no sistema | Escolha do Arthur, contra minha recomendação — ver Riscos. |
| Validade da carga | 15 minutos sem relato | Quem desloga com o porão cheio esconderia material do esquadrão indefinidamente. |
| Sistema da obra | Coluna nova, carimbada pelo sistema corrente | Sem ela o transbordo "outras obras do sistema" não é implementável. |
| Onde aparece o crédito | Rodapé da mensagem da obra | Junto do dado que a mensagem já mostra, sem criar mensagem nova nem ciclo de vida novo. |

## Mudanças no `ed_parser`

**`_registros` vira `registros`** (público). O módulo novo do cliente precisa do
mesmo fluxo de linhas JSON; duplicar a leitura seria manter dois parsers do
mesmo arquivo.

**`Instalacao` ganha `sistema: str = ""`.** Preenchido durante
`extrair_instalacoes`: o laço passa a rastrear o sistema corrente a cada
registro que o carrega — `FSDJump`, `Location`, `Docked`, `SupercruiseExit` —
e carimba esse valor na obra quando o `ColonisationConstructionDepot` dela
aparece.

Rastrear o sistema corrente é melhor que ler o `StarSystem` do `Docked` da
própria obra: obra planetária costuma ser aproximada sem pouso, e o
`ApproachSettlement` não traz `StarSystem`.

## O módulo novo do cliente: `comandante.py`

Uma responsabilidade: montar o retrato do comandante para enviar.

```python
@dataclass
class Entrega:
    quando: str          # timestamp ISO do evento, como veio do Journal
    market_id: int
    material: str        # nome localizado
    quantidade: int


@dataclass
class RetratoComandante:
    carga: dict          # {material localizado: quantidade}
    alvo_market_id: int | None
    alvo_sistema: str
    entregas: list       # Entrega


def ler_cargo_json(pasta=None) -> dict
def extrair_entregas(caminho_log) -> list
def alvo_atual(caminho_log) -> tuple      # (market_id | None, sistema)
def montar_retrato(caminho_log, pasta=None) -> RetratoComandante
```

`ler_cargo_json` devolve `{}` quando o arquivo não existe, está vazio ou está
malformado. O jogo reescreve esse arquivo enquanto o cliente lê; uma leitura no
meio da escrita não pode derrubar o ciclo.

`alvo_atual` é o `MarketID` do último `ColonisationConstructionDepot` do log,
com o sistema corrente naquele ponto.

## O endpoint `POST /comandante`

Mesmo cabeçalho `X-API-Token` do `/logdata`; `conferir_token` já devolve o nome
de quem enviou, e é dele que sai o `quem`.

```json
{ "carga": [{"material": "Alumínio", "quantidade": 720}],
  "alvo": {"market_id": 4251780355, "sistema": "Wregoe KP-E c25-11"},
  "entregas": [{"quando": "2025-05-20T17:37:50Z", "market_id": 4251780355,
                "material": "Alumínio", "quantidade": 720}] }
```

Resposta `{"status": "ok"}`. Diferente do `/logdata`, este endpoint **não
depende do Discord estar pronto** — ele só escreve no banco. Um `503` aqui
custaria a carga do ciclo inteiro por nada.

## Estado novo no banco

```sql
CREATE TABLE IF NOT EXISTS carga (
    quem       TEXT    NOT NULL,
    material   TEXT    NOT NULL,
    quantidade INTEGER NOT NULL,
    alvo       INTEGER,
    sistema    TEXT    NOT NULL DEFAULT '',
    quando     TEXT    NOT NULL,
    PRIMARY KEY (quem, material)
);

CREATE TABLE IF NOT EXISTS entregas (
    quando     TEXT    NOT NULL,
    market_id  INTEGER NOT NULL,
    material   TEXT    NOT NULL,
    quem       TEXT    NOT NULL,
    quantidade INTEGER NOT NULL,
    PRIMARY KEY (quando, market_id, material, quem)
);
```

E `instalacoes` ganha `sistema TEXT NOT NULL DEFAULT ''`, pelo mesmo `_migrar`
que já acrescenta colunas sem recriar a tabela.

**`carga` é substituída por completo** a cada relato: apaga as linhas daquele
`quem` e insere as novas. Sem delta, sem acúmulo, autocorrigindo.

Dois campos se chamam `quando` e significam coisas diferentes: em `carga` é a
hora em que o **servidor recebeu** o relato (é ela que a validade de 15 minutos
mede); em `entregas` é o timestamp do **evento no Journal**, que vem do cliente
e é parte da chave de deduplicação.

`alvo` e `sistema` se repetem em cada linha de `carga` da mesma pessoa. É
denormalização deliberada: a substituição por completo apaga e reinsere tudo de
uma vez, e uma tabela separada só para esses dois campos custaria um join para
não ganhar nada.

**`entregas` usa `INSERT OR IGNORE`.** O cliente reenvia a sessão inteira todo
ciclo; a chave primária composta descarta o que já está lá. Depois de um
restart do Render, os clientes reabastecem a tabela sozinhos no ciclo seguinte.

Limite conhecido e aceito: entregas de sessões anteriores vivem em Journals
antigos, que `encontrar_log_mais_recente` não lê, e somem quando o disco do
Render é reciclado. Não há resgate pelo canal — ver a seção do rodapé de
crédito, onde isso é explicado.

## A cascata de atribuição

Módulo novo no servidor, `transito.py`, com uma função pura:

```python
def atribuir(carga, obras_abertas, alvo_market_id, sistema) -> dict
```

Entra o porão de uma pessoa e as obras abertas; sai `{market_id: {material:
quantidade}}`. Três degraus, nesta ordem:

1. **A obra do alvo**, até o teto do que falta lá para aquele material;
2. **O excedente transborda** para as outras obras abertas do mesmo `sistema`,
   da que mais precisa daquele material para a que menos precisa, sempre
   respeitando o teto de cada uma;
3. **O que ainda sobrar é descartado** — não é carga de colonização.

Material que nenhuma obra aberta precisa não entra em degrau nenhum.

Obra com `sistema = ''` (vinda da reconciliação do canal, que não carrega essa
informação) não participa do degrau 2. Volta a participar quando alguém
reportar a obra de novo. É o mesmo comportamento que o `market_id` já tem.

## A coluna "A caminho" no consolidado

`consolidar()` passa a receber um segundo argumento opcional com o total em
trânsito por material, e `LinhaConsolidada` ganha `a_caminho: int = 0`.

```
Material                  |  Faltam | A caminho | Obras
-------------------------------------------------------
Steel                     |   24500 |      1440 |     3
```

Carga cujo `quando` tem mais de **15 minutos** é ignorada na soma. A coluna some
da tabela quando ninguém tem nada a caminho, para não ocupar largura à toa.

A ordenação continua por `faltando` decrescente — não por "faltando menos o que
vem a caminho". O que a lista responde é "quanto esta obra ainda precisa", e
carga a caminho pode evaporar (o piloto desloga, vende, muda de ideia).

**Quando a coluna atualiza:** no próximo relato de obra aceito, não no instante
em que a carga muda. O `/comandante` só escreve no banco; quem mexe na mensagem
do Discord continua sendo o `/logdata`, pelos gatilhos já definidos no
subsistema 1. Fazer a carga disparar atualização de mensagem colocaria o canal
a reboque de um POST por pessoa a cada 60 s — exatamente o churn que os
gatilhos existem para evitar. A consequência a aceitar: num período sem nenhum
relato de obra, a coluna fica velha, e pode inclusive mostrar carga que a
validade de 15 minutos já teria descartado numa leitura nova.

## O rodapé de crédito

A mensagem de cada obra ganha uma segunda linha de subtexto, somando a tabela
`entregas` por pessoa:

```
-# atualizado por Eruel às 14:32 UTC
-# entregue: Eruel 1440t · btpopov 720t
```

Ordenado do maior para o menor, cortado no orçamento de 2000 caracteres da
própria mensagem de obra, fechando com `+N` quando não couber. Sem entrega
registrada, a linha não aparece.

**A reconciliação NÃO relê essa linha do canal**, e isso é uma correção a uma
versão anterior desta spec. Reler duplicaria: o cliente reenvia todas as
entregas da sessão a cada ciclo, então o total lido do rodapé somaria com as
entregas reenviadas e o crédito dobraria a cada restart no meio de uma sessão.

O formato continua sendo relível (`creditos_na_mensagem` existe e é testada de
ida e volta), porque é a peça que uma reconciliação futura precisaria — mas ela
só faz sentido com armazenamento persistente, não com o disco efêmero de hoje.

Consequência aceita: o crédito cobre o que está no Journal atual de cada
cliente. Restart no meio da sessão não perde nada, porque os clientes
reabastecem em até 60 s. Entre sessões, recomeça.

## Testes

`comandante.py`:

- `Cargo.json` ausente, vazio, malformado e truncado no meio devolvem `{}`;
- `Cargo.json` válido vira `{material localizado: quantidade}`;
- entregas extraídas de `ColonisationContribution`, inclusive várias no mesmo evento;
- alvo é o último `ColonisationConstructionDepot`, com o sistema corrente daquele ponto;
- log sem nenhum depot devolve alvo `None`.

`ed_parser`:

- `Instalacao.sistema` vem do sistema corrente, não do `Docked` da própria obra;
- obra vista só por `ApproachSettlement`, depois de um `FSDJump`, tem sistema;
- `registros` continua devolvendo o mesmo que `_registros` devolvia.

`transito.atribuir`:

- tudo cabe no alvo;
- excedente transborda para a segunda obra do sistema, da que mais precisa;
- excedente que não cabe em nenhuma é descartado;
- obra de outro sistema não recebe transbordo;
- obra com `sistema = ''` não recebe transbordo;
- material que ninguém precisa é ignorado;
- alvo `None`: tudo vai direto para o degrau 2.

Endpoint e banco:

- `/comandante` sem token é 401; com token válido grava e devolve `ok`;
- `/comandante` funciona com o bot do Discord fora do ar;
- reenviar as mesmas entregas duas vezes não duplica;
- relatar carga de novo substitui a anterior daquela pessoa, não soma;
- carga de outra pessoa não é afetada.

Consolidado e rodapé:

- coluna "A caminho" aparece com carga viva e some sem ela;
- carga com mais de 15 minutos é ignorada;
- a coluna é calculada no momento em que a mensagem é montada, e não há caminho
  do `/comandante` para o Discord;
- a ordenação não muda por causa da carga a caminho;
- rodapé de crédito ordenado e cortado, com `+N`;
- sem entregas, sem linha de rodapé;
- o crédito é relível de ida e volta pelo formato;
- a reconciliação do canal **não** grava crédito.

## Fora de escopo

- **Onde comprar o que falta** (integração com o Ardent): subsistema 3, spec própria.
- Usar `MarketBuy` para qualquer coisa. Ele foi avaliado como fonte da carga e
  descartado; fica registrado para não ser reavaliado do zero.
- Histórico de entregas por sessão antiga, além do que o canal recupera.
- Ranking de esquadrão como mensagem própria.

## Riscos

**Atribuição errada esconde material — e foi decisão consciente.** Eu recomendei
não atribuir a carga a nenhuma obra específica, só somar por material no
agregado: sempre correto, zero palpite. O Arthur escolheu a atribuição por
última obra visitada, com transbordo. O modo de falha é concreto: o piloto que
carrega Steel, é marcado como levando para a obra A e some para outro sistema
faz o consolidado da obra A mostrar menos Steel faltando do que realmente falta,
por até 15 minutos. As duas proteções contra isso são o teto por obra e a
validade — nenhuma das duas elimina o caso, só o limitam.

**O formato do `Cargo.json` é premissa, não fato.** Nenhuma cópia foi
inspecionada. Se a forma real divergir, o parsing muda; o resto do desenho não.

**Carga a caminho é dado sem confirmação.** Ninguém promete entregar o que está
no porão. A coluna informa, não reserva. Se o esquadrão passar a tratá-la como
promessa, a frustração é de expectativa, não de software — está aqui registrado
de propósito.

**Um endpoint a mais por ciclo por pessoa.** Com o esquadrão em dois, é
irrelevante. Com vinte clientes num ciclo de 60 s, são 20 requisições/minuto no
plano gratuito do Render — ainda folgado, mas é o número a observar se o grupo
crescer.
