# Consolidado de materiais do esquadrão

Data: 2026-09-05
Status: aguardando revisão

## Problema

O bot publica uma mensagem por obra, cada uma com sua tabela de materiais. Isso
responde "o que falta *nesta* obra" e não responde a pergunta que o esquadrão
faz antes de sair da estação: **"o que eu carrego?"**

Com várias obras abertas ao mesmo tempo, descobrir isso hoje é abrir cada
mensagem do canal e somar de cabeça. O piloto sai com o porão cheio da coisa
errada, ou faz duas viagens onde cabia uma.

O dado necessário já chega ao servidor — cada relato traz requerido e fornecido
por material. Falta agregá-lo.

### O obstáculo escondido

`verificar_finalizacoes` (`servidor.py:150`) chama `marcar_finalizado`
incondicionalmente depois de `TEMPO_FINALIZACAO_HORAS` sem atualização:

```python
if horas < TEMPO_FINALIZACAO_HORAS:
    continue
...
banco.marcar_finalizado(registro.instalacao.nome)   # sempre, completa ou não
```

O ✅ só é adicionado quando todos os materiais estão completos, mas a linha vira
`finalizado=1` de qualquer jeito. Hoje **`finalizado` significa "ninguém
reportou nas últimas 2 horas"**, não "obra pronta".

Um consolidado construído sobre `listar(pendentes=True)` esconderia exatamente
as obras que mais precisam de material — as que ninguém visitou hoje. Corrigir o
sentido de `finalizado` é pré-requisito, não melhoria oportunista.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Onde o cálculo vive | Módulo novo `consolidado.py` | Agregação sobre estado do servidor. O `ed_parser` já tem 8,4 KB e é compartilhado com o cliente. |
| Chave de agrupamento | Nome **localizado** do material | As linhas vindas da reconciliação do canal têm `nome_interno=""`; agrupar pelo interno colapsaria todas num balde só. |
| `faltando` negativo | Piso em zero | Entrega a mais numa obra viraria desconto no total de outra. |
| Sentido de `finalizado` | Passa a marcar só quando os materiais estão completos | Sem isso o consolidado fica vazio na prática. |
| Onde aparece | Uma mensagem no canal do Discord | É onde o esquadrão coordena. Reaproveita o mecanismo que já existe. |
| Atualização | Edita no lugar; reposta em eventos discretos | Canal limpo no caso comum, visível quando há notícia. |
| Intervalo mínimo entre reposts | 30 min | Contém a frequência do gatilho "material zerou", que é o mais sensível dos quatro. |
| Nomes das obras na mensagem | Sim, logo abaixo do cabeçalho | "3 obras" diz quantas, não quais — e "quais" é o que decide se a viagem vale. |
| Prefixo do nome da obra | Cortado (`Construction Site:`) | É idêntico em todas e custa ~30 caracteres por linha do orçamento de 2000. |
| Estouro de 2000 caracteres | Corta os menores e resume numa linha | A lista já está ordenada do maior faltante; o que sai é sempre o que menos importa. |
| Mensagem fixada | Não | O repost quebraria o pin (mensagem nova, desfixar e refixar). O híbrido já resolve visibilidade. |

## O cálculo

```python
@dataclass
class LinhaConsolidada:
    material: str        # nome localizado
    faltando: int        # soma, com piso em zero por obra
    obras: int           # em quantas obras esse material ainda falta


@dataclass
class Retrato:
    linhas: list         # LinhaConsolidada, ordenadas
    obras: frozenset     # nomes das obras que ainda precisam de algo


def consolidar(instalacoes) -> Retrato
```

Função pura: entra uma lista de `ed_parser.Instalacao`, sai o retrato com as
linhas ordenadas por `faltando` decrescente. Sem banco, sem Discord, sem
relógio.

O campo `obras` existe porque dois dos quatro gatilhos são sobre obras, não
sobre materiais, e não seriam calculáveis só a partir das linhas: elas somam
materiais e perdem de vista quem contribuiu. Guardar o conjunto de nomes no
retrato mantém a comparação entre dois retratos suficiente para os quatro
gatilhos, sem o decisor precisar do banco.

É `frozenset` de propósito: a igualdade sem ordem é a semântica que os gatilhos
querem (`antes == depois` não pode depender da ordem em que as obras saíram do
banco). Quem ordena para exibição é o formatador.

Regras:

- material com `faltando <= 0` numa obra não contribui e não conta em `obras`;
- obra sem nenhum material faltando não entra;
- desempate por nome do material, para a saída ser estável entre chamadas.

## Ciclo de vida da mensagem

### Estado

Tabela nova, no padrão de `_migrar` (sem recriar nada existente):

```sql
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
)
```

Duas chaves: `consolidado_message_id` e `consolidado_ultimo_repost`.

### Reconciliação

O disco do Render é efêmero: a `meta` some a cada restart, junto com o resto do
banco. Sem tratamento, cada restart posta um consolidado novo e os antigos viram
lixo permanente no canal.

Na reconciliação, além das obras, o bot procura a própria mensagem de
consolidado pelo cabeçalho:

```
🧾 **Consolidado do esquadrão**
```

O cabeçalho não colide com `_NOME_NA_MENSAGEM`, que exige `📍 **Materiais para
instalação:**` — então `nome_na_mensagem` devolve `None` para o consolidado e a
reconciliação de obras já o ignora sozinha.

- achou uma: adota o `message_id`;
- **achou mais de uma: adota a mais recente e apaga as outras** — é isto que
  impede o acúmulo;
- não achou: a próxima atualização posta a primeira.

`consolidado_ultimo_repost` é reconstruído a partir do `created_at` da mensagem
adotada. Sem isso, todo restart contaria como "faz mais de 12h" e dispararia um
repost desnecessário.

### Quando atualiza

Em `receber_dados`, depois do `banco.salvar`, e **só quando o relato foi
aceito** — `ignorado` significa que nada mudou.

O servidor calcula o consolidado antes e depois do save e compara os dois
retratos:

| Situação | Comparação | Ação |
|---|---|---|
| obra nova entrou | nome em `depois.obras` e não em `antes.obras` | repost |
| obra ficou pronta | nome em `antes.obras` e não em `depois.obras` | repost |
| material zerou | material presente em `antes.linhas` e ausente de `depois.linhas` | repost |
| passou o tempo | `agora - ultimo_repost > 12h` | repost |
| cooldown | `agora - ultimo_repost < 30min` | edita — vence todos os gatilhos acima |
| qualquer outra mudança | `antes != depois` | edita no lugar |
| nada mudou | `antes == depois` | não faz nada |

Material que zerou some das linhas por construção: `consolidar` já exclui
`faltando <= 0`. Então "zerou" e "sumiu das linhas" são a mesma condição, e não
há caso de material presente nos dois retratos com `faltando` zero.

"Repost" é apagar a mensagem anterior e postar uma nova, como já é feito com as
mensagens de obra. "Editar" é `message.edit()` na mensagem existente.

A decisão é uma função pura sobre `(antes, depois, ultimo_repost, agora)`, então
os gatilhos são testáveis sem Discord.

## Formato da mensagem

```
🧾 **Consolidado do esquadrão** `3 obras`
Pedder's Forge · Montes Biological Enterprise · Victoria Wolf Steel

Material                  |  Faltam | Obras
------------------------------------------
Steel                     |   24500 |     3
Computer Components       |    8200 |     2
...
+7 materiais menores (3140 no total)

-# atualizado às 14:32 UTC
```

### Os nomes das obras

Linha logo abaixo do cabeçalho, nomes separados por `·`, ordenados
alfabeticamente — ordem estável, para a mensagem não se reescrever sozinha
quando o banco devolver as linhas em outra ordem.

O prefixo de construção é cortado: `MARCA_CONSTRUCAO` (`"Construction Site:"`)
já existe no `ed_parser`, e o nome exibido é o que vem depois dele. Quando o
nome não tem o prefixo, ou o que sobra ficaria vazio, usa-se o nome inteiro.

### O orçamento de 2000 caracteres

Prioridade, do que nunca sai para o que sai primeiro:

1. cabeçalho, contagem de obras e rodapé;
2. a linha de nomes das obras, até **300 caracteres**; passando disso, entram os
   que couberem e fecha com `+N outras`;
3. as linhas de material, na ordem decrescente já estabelecida;
4. a linha de resumo do que foi cortado.

Os nomes vêm antes dos materiais porque respondem "essa lista é sobre o quê" —
sem isso, os números não significam nada. Quando nada foi cortado, nem a linha
`+N outras` nem a de resumo aparecem.

## Testes

`consolidar()`:

- soma o mesmo material em obras diferentes;
- piso em zero: obra com entrega a mais não reduz o total das outras;
- agrupa por nome localizado, com linhas de `nome_interno` vazio no meio;
- obra completa não entra;
- ordenação decrescente, desempate estável por nome.

Gatilhos, um teste por linha da tabela, mais o cooldown vencendo cada um dos
quatro.

Mensagem:

- cabe em 2000 caracteres com muitos materiais, e a linha de resumo bate com o
  que foi cortado;
- sem corte, não há linha de resumo;
- o cabeçalho do consolidado não é reconhecido por `nome_na_mensagem`;
- os nomes das obras aparecem, sem o prefixo `Construction Site:`, em ordem
  alfabética;
- obra cujo nome não tem o prefixo aparece inteira;
- com muitas obras, a linha de nomes é cortada em 300 caracteres e fecha com
  `+N outras`, e o `N` bate com o que ficou de fora;
- a ordem das obras na mensagem não muda quando o `frozenset` é iterado em
  ordem diferente.

Reconciliação:

- uma mensagem no canal: adota o id e o `created_at`;
- três mensagens: adota a mais recente e apaga as outras duas;
- nenhuma: não quebra, e a próxima atualização posta.

`finalizado`:

- obra parada há mais de 2h com material faltando **continua pendente**;
- obra com tudo completo há mais de 2h é marcada finalizada e ganha o ✅.

## Fora de escopo

- **Onde comprar o que falta** (integração com o Ardent) e **carga do
  comandante** (`Cargo.json`, `MarketBuy`): subsistemas próprios, cada um com
  spec e plano em separado. Este consolidado é a entrada dos dois.
- Fixar a mensagem no canal.
- Comando slash.
- Índice único parcial em `market_id` — melhoria já adiada por decisão anterior.

## Riscos

**Obra abandonada infla o total pra sempre.** Consequência direta de corrigir o
sentido de `finalizado`: nada mais tira do consolidado uma obra que ninguém vai
terminar. Resolver exigiria uma noção de "abandonada" que não existe hoje, e a
régua é decisão do esquadrão, não do código. Fica registrado; se doer, vira
trabalho próprio.

**Duas obras de mesmo nome se sobrescrevem.** `nome` é PRIMARY KEY, então obras
homônimas em sistemas diferentes já colidem hoje — o consolidado herda isso e
mostraria só uma. Improvável (os nomes vêm do assentamento) e é exatamente o
caso que o índice único parcial em `market_id` resolveria.

**Mudança de comportamento em produção.** O sentido de `finalizado` muda para um
bot que já está no ar, com 8 obras no banco. Depois do deploy, obras hoje
marcadas finalizadas por inatividade continuam finalizadas — a correção só vale
dali pra frente. Não é preciso migrar: obra que ainda importa volta a ser
reportada e o `ON CONFLICT` a ressuscita com `finalizado=0`.
