# Cliente com painel local e uso pelo esquadrão

Data: 2026-09-03
Status: aprovado, aguardando plano de implementação

## Problema

O cliente hoje é um loop de terminal que lê o Journal, envia as instalações
alteradas e imprime o resultado. Três coisas doem:

1. **Um envio que falha some.** `sincronizar` grava a assinatura do payload
   mesmo quando o POST falhou, porque `enviar_para_api` engole a exceção e não
   devolve nada. Aquele estado só é reenviado quando os materiais mudarem de
   novo — uma queda de rede ou o Render hibernando custa a atualização.
2. **Falha silenciosa.** O envio imprime `[API] 404 - Not Found` e segue. Foi
   exatamente assim que um `API_ADRESS` errado passou despercebido: servidor no
   ar, cliente rodando, canal vazio, nenhum erro visível.
3. **Não dá para saber se está funcionando** sem ler o terminal.

E o objetivo novo: o esquadrão inteiro rodando o cliente, o que traz
autenticação por pessoa e concorrência entre relatos da mesma obra.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Estrutura do cliente | Um processo, servidor HTTP embutido numa thread | O painel lê o estado vivo, não um retrato salvo. Zero dependência nova. |
| Concorrência entre relatos | Uma mensagem por instalação; servidor aceita só o mais completo | Evita o canal piscando e o rate limit do Discord com N clientes. |
| Painel | Só leitura, sem ações | Não abre porta de escrita na máquina de quem roda. |
| Distribuição | Zip com `.bat`; a pessoa instala Python uma vez | Sem etapa de build, atualizar é baixar o zip novo. |
| Autenticação | Um token por pessoa | Revogar individualmente e saber quem reportou. |
| Crédito no Discord | Rodapé discreto com nome e hora | Responde "esse dado está fresco?" sem poluir a tabela. |

### Duas propostas descartadas por medição

**Leitura incremental do Journal.** Descartada. Uma leitura + parsing completo
do Journal de uma sessão de 3h30 (1,4 MB, 1172 linhas) leva **15 ms**;
extrapolando, ~50 ms para uma sessão de 12h e ~101 ms para uma de 24h. Contra
um ciclo de 60 s, isso é 0,08% e 0,17% do tempo. A complexidade — offset por arquivo, linha pela metade porque o jogo
estava escrevendo, detectar troca de arquivo — não compra nada mensurável e
introduz justamente a classe de erro que ela deveria evitar.

**Ler Journals rotacionados.** Descartada: o problema não existe. Os quatro
arquivos em `journals/` têm o mesmo timestamp no nome
(`Journal.2025-05-20T141829.01`) e cada um é prefixo exato do maior (507 → 905
→ 938 → 1172 linhas). São cópias manuais do mesmo arquivo, não rotação. O jogo
anexa a um arquivo por sessão: os timestamps dentro do log são estritamente
crescentes e não há nenhum evento `Continued`. A troca de arquivo entre sessões
já é resolvida por `encontrar_log_mais_recente()`.

## Arquitetura do cliente

Um processo, duas tarefas, ligadas por um objeto de estado:

```
cliente.py           ponto de entrada: sobe as duas tarefas
├── monitor.py       loop: Journal -> ed_parser -> POST     (só escreve estado)
├── estado.py        EstadoCliente: o contrato entre os dois
└── painel.py        http.server numa thread, 127.0.0.1      (só lê estado)
```

`EstadoCliente` guarda:

- `journal_atual` — caminho do arquivo sendo lido
- `ultima_leitura` — quando o loop rodou pela última vez
- `ultimo_envio_ok` — quando um POST retornou 2xx pela última vez
- `ultimo_status_http` — código do último POST
- `instalacoes` — nome, percentual e materiais faltantes do último ciclo
- `erros` — os N erros mais recentes, com horário e mensagem

O monitor só escreve, o painel só lê. Cada um é testável sozinho: o painel com
um estado montado à mão, o monitor sem painel nenhum.

`iniciar.bat` sobe o Python e abre o navegador em `http://127.0.0.1:8765`.

### Confiabilidade do envio

`enviar_para_api` passa a devolver sucesso ou falha. `sincronizar` só grava a
assinatura **depois** de um envio bem-sucedido, então um envio que falhou é
naturalmente reenviado no ciclo seguinte, sem fila nem backoff próprio: o
próprio ciclo de 60 s é a retentativa.

Sucesso é status 2xx. Qualquer outra coisa — 401, 404, 5xx, timeout, exceção de
rede — entra em `erros`, aparece no painel e não grava a assinatura.

### Configuração

`config.txt` ao lado do `.bat`, formato `CHAVE=VALOR`:

```
API_TOKEN=<token da pessoa>
API_URL=https://botelitedangerous.onrender.com/logdata
```

`config.txt` em vez de `.env` porque o Windows esconde extensões e arquivos
começando com ponto. O zip leva um `config.exemplo.txt` com `API_URL` já
preenchido — é igual para todos, só o token muda.

Sem `config.txt`, ou sem token, o cliente não entra no loop: diz o que falta, no
terminal e no painel, e para.

### Painel

Duas rotas explícitas, nunca a pasta — `config.txt` não pode ser servido:

- `GET /` — a página
- `GET /estado.json` — o estado, buscado pela página a cada 5 s

Ligado só em `127.0.0.1`. Porta 8765; se ocupada, tenta as seguintes e informa
no terminal qual pegou.

## Mudanças no servidor

### Tokens por pessoa

`API_TOKEN` (um) vira `API_TOKENS`, uma linha por pessoa:

```
Arthur=<token-gerado-para-o-arthur>
Fulano=<token-gerado-para-o-fulano>
```

- Token desconhecido → 401.
- Token conhecido → o servidor tem o nome, que vai para o rodapé.
- Se apenas `API_TOKEN` existir, vale como uma entrada sem nome, para o deploy
  atual não quebrar durante a transição.
- Comparação com `secrets.compare_digest`, para o tempo de resposta não revelar
  quanto do token está correto.

### Arbitragem do relato mais completo

O payload ganha `market_id`. O servidor chaveia por ele, caindo para o nome
quando ausente (cliente antigo).

Ao receber, compara o total fornecido com o armazenado:

- **menor ou igual** → responde `200 {"status": "ignorado"}` e não toca na
  mensagem do Discord. Para o cliente isso é sucesso: ele grava a assinatura e
  não reenvia, porque o servidor recebeu e decidiu — não é falha.
- **maior** → apaga a anterior e posta a nova, com rodapé
  `atualizado por Fulano às 14:32`

Com cinco clientes reportando a mesma obra, quatro viram no-op — é isso que
resolve o rate limit, sem lógica de throttling.

O total fornecido só cresce ao longo de uma construção, então "maior total" é
uma aproximação segura de "mais recente". A premissa cairia se uma obra
reiniciasse no mesmo `MarketID`; o Arthur, que joga isso, confirmou nunca ter
visto acontecer. Se um dia acontecer, o sintoma é uma mensagem que trava num
estado antigo e ignora relatos novos.

### Banco

Duas colunas novas em `instalacoes`: `market_id` e `reportado_por`. Já existe
tabela em produção, então a criação usa `ALTER TABLE` guardado por checagem de
coluna existente, em vez de recriar.

## Testes

Além dos 68 atuais, que seguem verdes:

- `EstadoCliente` isolado.
- Painel numa porta efêmera: `/estado.json` devolve o formato esperado, e
  **`/config.txt` não é servido** — regressão de segurança que não pode voltar
  em silêncio.
- Retentativa: envio que falha não grava a assinatura, e o ciclo seguinte
  reenvia. Fake que falha uma vez e depois aceita.
- Servidor: token → nome; 401 para desconhecido; relato menos completo
  ignorado sem tocar no Discord; relato mais completo aceito; rodapé correto.
- Config: ausência de `config.txt` ou de token impede o loop, com mensagem
  clara.

## Fora de escopo

- Empacotar em `.exe` (PyInstaller e build no CI) — a distribuição por zip
  dispensa.
- Ações pelo painel (pausar, reenviar, trocar Journal) — manteria o painel só
  de leitura.
- Disco persistente no Render. O filesystem é efêmero e disco persistente não
  existe no plano gratuito; a reconciliação pelo canal já cobre.

## Riscos

- **Antivírus ou firewall do Windows** pode reclamar de um processo Python
  abrindo porta local. Mitigação: só `127.0.0.1`, nunca `0.0.0.0`.
- **A pessoa fecha o terminal** e o cliente para. Sai do escopo desta rodada;
  se incomodar, vira um atalho na inicialização depois.
- **Administrar a lista de tokens** vira trabalho manual do Arthur. Aceito
  conscientemente em troca de poder revogar individualmente.
