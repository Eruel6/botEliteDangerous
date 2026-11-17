# Aba Exploração: cards, modais e tabela de preços

Data: 2026-11-16 · Branch: `worktree-aba-exploracao`

## Por quê

Hoje a aba Exploração é uma sequência de blocos de texto com tabelas longas
soltas. O Arthur quer ver o essencial de relance (o que está a bordo, o que já
vendeu, a carreira) e abrir o detalhe só quando quiser. Também quer consultar
os preços da Vista Genomics sem sair do painel.

## Objetivos

- Cards de resumo no topo da aba. Clicar num card abre um modal com a tabela detalhada.
- Tabela de preços das 96 espécies embaixo dos cards.
- Visual mais caprichado: hover, transições e animação do modal, no tema laranja/escuro atual.

## Fora do escopo

- Planejamento de rota ou sugestão de onde coletar.
- Mudanças na aba Colonização (ela só divide os estilos base).

## Abordagens

1. **HTML/JS puro no `painel.html` com `<dialog>` nativo** (escolhida). O painel
   não tem build e é servido localmente. O `<dialog>` já traz foco, Esc e backdrop.
2. Biblioteca de UI via CDN: peso e dependência de rede num painel que roda offline. Descartada.
3. Página separada para os detalhes: perde o contexto e duplica o polling. Descartada.

## Design

### Cards

| Card | Conteúdo | Modal |
|---|---|---|
| A bordo | total de amostras; **prováveis sem multiplicador** (soma dos preços base das amostras com bônus provável); **prováveis com multiplicador** (a mesma soma ×5) | tabela de amostras a bordo (Espécie, Planeta, Base, Bônus) e dados de exploração |
| Vendido | amostras vendidas e total (journals) | tabela de vendidas, aviso de corte e perdas por morte |
| Carreira (jogo) | amostras, lucro e primeiras descobertas do evento Statistics | sem modal (só números); oculto se não houver Statistics |
| Primeiro a… | descobrir sistema/corpo, mapear, pisar | tabela de corpos |
| Médias | por amostra, por planeta, por sessão | sem modal |

- O backend (`Historico._a_bordo`) ganha `provaveis_quantidade`, `provaveis_base`
  e `provaveis_com_bonus`. `total_base` e `total_com_bonus` continuam existindo, por compatibilidade.
- **Multiplicador:** continua ×5 (base + 4× de bônus de primeiro registro), o
  valor usado pela comunidade (Canonn, ed-dsn) desde o reajuste da Vista em
  2022. Não está confirmado num journal real do Arthur. Por isso:
  - o card escreve "com bônus (×5, estimado)";
  - quando um `SellOrganicData` trouxer `Bonus > 0`, o resumo passa a expor o
    multiplicador observado, `(Value + Bonus) / Value`, médio. O card Vendido o mostra, e
    o rótulo do card A bordo troca "estimado" por "observado ×N" se divergir de 5.
    O cálculo do a bordo continua usando a constante. A conferência é visual.

### Modal

- Um único `<dialog>` reaproveitado. Fecha com Esc, com clique no backdrop ou no botão ×.
- No polling de 5 s, se o modal estiver aberto, o conteúdo é trocado no lugar,
  sem fechar nem rolar para o topo (guarda o `scrollTop`).

### Tabela de preços

- O `/exploracao.json` ganha `precos: [{especie, base, com_bonus}]` (lista
  ordenada do maior para o menor) e `precos_atualizado_em`.
- Colunas: Espécie, Base, Com bônus (×5). Campo de busca por nome (sem acento,
  sem caixa). Rodapé com a data de atualização e a fonte.
- A tabela não é redesenhada no polling, porque os preços não mudam em execução. Assim a busca não se perde.

### Estilo

- Cards: hover com leve elevação (`translateY(-2px)`), borda laranja e brilho
  suave; cursor de mão e foco visível por teclado (os cards são `<button>`).
- Modal: fade e escala na abertura, backdrop escurecido com blur.
- Tabelas: linha com hover, números alinhados à direita com `tabular-nums`.
- `prefers-reduced-motion`: desliga as transições.

## Testes

- `provaveis_*` somam só as amostras prováveis; espécie sem preço não quebra a conta.
- Multiplicador observado: ausente sem venda com bônus; calculado com uma.
- `precos` vem ordenado e com `com_bonus = base × 5`.

## Com o construtor

Valores exatos de cor, sombra e tempo das transições; texto dos rótulos.
