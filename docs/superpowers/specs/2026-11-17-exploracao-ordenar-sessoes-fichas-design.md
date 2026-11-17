# Aba Exploração: ordenar tabelas, gráfico de sessões e ficha do gênero

Data: 2026-11-17 · Branch: `worktree-aba-exploracao` · Continua `2026-11-16-exploracao-cards-design.md`

## Por quê

O Arthur gostou dos cards e pediu mais três coisas:
- ordenar as tabelas;
- ver os ganhos de exobiologia por sessão;
- identificar mais fácil cada espécie dentro do planeta, por texto e por foto.

A aba continua sendo só para acompanhar o que ele já fez. Nada de planejar rota.

## Objetivos

1. **Ordenar:** clicar no cabeçalho de qualquer tabela da aba (os modais e os preços) ordena por aquela coluna; um segundo clique inverte. Uma seta ▲/▼ mostra a ordem atual. A ordem vale por tabela e se mantém no polling de 5 s.
2. **Sessões:** um card "Sessões" abre no modal um gráfico de barras SVG com as últimas 20 sessões, cada uma = um journal.
   - A amostra conta na sessão em que foi **coletada** (`ScanOrganic` Analyse), mesmo critério da média "por sessão" que já existe.
   - Vendidas entram pelo valor pago, em cor cheia (laranja). A bordo entra pelo valor estimado, em cor clara empilhada em cima.
   - Vendas sem par (sem sessão conhecida) ficam fora do gráfico.
   - Hover/foco mostra a data da sessão e os dois valores.
3. **Ficha do gênero:** clicar no nome de uma espécie (tabela de preços e tabelas dos modais) abre a ficha no mesmo `<dialog>`. Ela traz:
   - nome do gênero, descrição curta em PT-BR (aspecto e onde costuma aparecer);
   - **distância mínima entre amostras** (alcance da colônia clonal), com a fonte;
   - a **foto do gênero**, buscada na hora pela API da wiki Fandom, e o link para a página da wiki.
   - Botão "voltar" quando a ficha foi aberta de dentro de outro modal.

## Fora do escopo

- Foto por espécie ou por variante (a wiki só tem página por gênero).
- Guardar imagens no zip (direitos são do jogo e da wiki).
- Planejamento de rota, previsão de onde a espécie aparece.

## Abordagens

Para as fotos:
1. **API da wiki em tempo de execução** (escolhida). `https://elite-dangerous.fandom.com/api.php?action=query&titles=<Página>&prop=pageimages&pithumbsize=400&format=json&origin=*` devolve a miniatura do gênero; `origin=*` libera CORS. Testado em 2026-11-17: devolve imagem para 19 dos 21 gêneros, e o `static.wikia.nocookie.net` serve a imagem com referer `127.0.0.1` (200, webp).
2. URLs fixas no JSON: quebra quando a wiki renomeia o arquivo. Descartada.
3. Só link para a wiki: obriga a sair do painel. Descartada como principal, mas o link fica na ficha.

Para o gráfico: SVG desenhado à mão no JS, sem biblioteca (o painel não usa CDN).

## Design

### Dados dos gêneros: `generos_exobio.json` (novo, entra no zip)

```json
{"generos": {"Bacterium": {"wiki": "Bacterium", "distancia_m": 500, "fonte_distancia": "comunidade",
  "descricao": "…"}}}
```

- Os 21 gêneros da tabela de preços: Aleoida, Amphora Plant, Anemone, Bacterium, Bark Mounds, Brain Tree, Cactoida, Clypeus, Concha, Crystalline Shards, Electricae, Fonticulua, Frutexa, Fumerola, Fungoida, Osseus, Recepta, Sinuous Tubers, Stratum, Tubus, Tussock.
- `wiki`: título da página na Fandom. Testado: `Bark Mound`, `Crystalline Shard` e `Sinuous Tuber` ficam no singular. Se um gênero tiver `wiki: null`, a ficha fica sem foto, com link para a busca da wiki.
- `distancia_m` e `fonte_distancia`:
  - `"wiki"` quando a página da wiki traz o valor. Lidos em 2026-11-17: Aleoida 200, Amphora Plant 100, Cactoida 300, Clypeus 150, Concha 150, Fonticulua 500, Frutexa 150, Fungoida 300, Osseus 800, Stratum 500, Tubus 800, Tussock 200.
  - `"comunidade"` para os demais, com os valores difundidos pela comunidade: Bacterium 500, Electricae 1000, Fumerola 100, Recepta 150, Anemone 100, Bark Mounds 100, Brain Tree 100, Crystalline Shards 100, Sinuous Tubers 100.
  - A ficha mostra "(fonte: wiki)" ou "(comunidade — confira no Codex)". O Codex do jogo é a referência final.
- `descricao`: 1 a 2 frases em PT-BR, escritas por nós (não copiadas da wiki).
- Mapeamento espécie → gênero: o gênero é o nome da espécie na tabela de preços que bate com uma chave de `generos` (mais longa primeiro, sem diferenciar caixa: "Amphora plant" → "Amphora Plant"; "Bacterium Acies" → "Bacterium"). Espécie sem gênero conhecido → nome sem link.
- `precos_vista.py`/`exploracao.py`: o resumo ganha `generos` (o dicionário acima) e cada item de `precos` ganha `genero` (chave ou `null`). As amostras a bordo e vendidas ganham `genero` também.

### Sessões (backend)

- `resumo()["sessoes"]`: lista das 20 sessões mais recentes com coleta, em ordem cronológica, cada uma `{"sessao": str, "quando": str (timestamp da primeira coleta), "vendido": int, "a_bordo": int}`.
- `vendido` soma `valor` das vendidas cuja `sessao` é essa; `a_bordo` soma `valor_estimado` (sem `None`) das amostras a bordo dessa sessão.

### Ordenação (frontend)

- `tabelaTexto` ganha ordenação opcional: cada tabela tem uma chave estável (`"a_bordo"`, `"vendido"`, `"primeiros"`, `"precos"`); o estado `{coluna, desc}` por chave fica num objeto global e é reaplicado a cada redesenho.
- Comparação: colunas numéricas pelo valor numérico cru (não pelo texto "5,0 mi"); texto com `localeCompare('pt-BR')`; vazios sempre no fim.
- Na tabela de preços (desenhada uma vez), ordenar reordena as linhas sem perder o filtro da busca.

### Ficha (frontend)

- Reaproveita o `<dialog>`. `abrirFicha(genero)` guarda o modal anterior (se houver) para o "voltar".
- A foto: `fetch` da API com timeout de 8 s, resultado guardado em memória por gênero (uma busca por gênero por carga da página). Enquanto carrega mostra "carregando foto…"; se falhar ou não houver imagem, mostra "foto indisponível" e o link.
- `<img>` com `alt` = nome do gênero, `loading="lazy"`, largura máxima 100%, altura máxima 260 px.
- O polling de 5 s não re-renderiza a ficha aberta (ela não depende do resumo).

### Estilo

Segue o padrão da entrega anterior: paleta laranja/escuro, `prefers-reduced-motion`, nomes clicáveis com sublinhado pontilhado e hover laranja, cabeçalhos ordenáveis com cursor de mão e foco visível.

## Testes

- Mapeamento espécie → gênero para os 96 preços: todos os 96 têm gênero (nenhum `null`).
- `generos_exobio.json` tem os 21 gêneros, cada um com `descricao` não vazia e `distancia_m` > 0.
- Sessões: soma por sessão de coleta; venda sem par fica fora; corte em 20; ordem cronológica.
- JS: ordenar número vs texto, inverter, vazios no fim, ordem mantida após `pintarExploracao`; busca + ordenação juntas; ficha com foto ok / falha (fetch falso); gráfico desenha uma barra por sessão.

## Com o construtor

Texto das descrições (curto, factual), cores exatas das barras, layout da ficha.
