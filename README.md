# Sonhos e preços proféticos

Página que reúne os sonhos, visões e palavras proféticas publicados no [propheticmoney.com](https://propheticmoney.com/) e a **Lista Lucas Borin** (lista de preços proféticos por moeda), organizados em:

- **Timeline de acontecimentos futuros**: um gráfico de linhas, uma por moeda, passando pela sequência que os sonhos descrevem (subida das cripto, gatilho, flash crash, colapso do sistema, ouro e prata, memecoins, novo sistema financeiro, transferência de riqueza).
- **Linha do tempo dos sonhos**: cada sonho na data em que foi recebido ou compartilhado, com o veredito que o site ou a lista deram.
- **Prazos marcados**: para quando cada previsão apontava.
- **Moedas e preços**: a escada de preços sonhados por moeda, comparada com o preço real de mercado ("já bateu" ou "ainda não bateu").

Português em `/` e inglês em `/eng`.

## Como funciona

| Parte | Arquivo |
|---|---|
| Página (HTML único, D3) | `app/template.html` |
| Montagem da página | `app/build.py` |
| Sincronização diária | `app/sync.py` |
| Servidor e agendador | `app/server.py` |
| Dados iniciais | `data/seed/` (`dataset.json`, `market.json`, `state.json`) |

Todo dia à **meia-noite de Nova York** (America/New_York, com horário de verão), o servidor:

1. Busca os posts novos do propheticmoney.com pela API pública do WordPress.
2. Classifica cada post **por regras, sem IA**: profeta e data pelo padrão "Prophecy by X on M/D/YY", tipo (sonho, visão, palavra), tema pelas categorias do site, prazo ("in 2027", "by September 2026"), preços citados ("$7 XRP", "Bitcoin to $150K") e o acontecimento futuro por palavras-chave.
3. Lê de novo as páginas de preço de cada moeda e as compilações "Other Prophecies" e adiciona as linhas novas.
4. Atualiza as cotações (Binance, KuCoin, Gate.io, MEXC, GeckoTerminal, Yahoo Finance) e recalcula se cada preço sonhado já foi atingido.
5. Remonta a página.

Os posts novos entram com o título original (em inglês) como resumo. A base inicial foi resumida em português, classificada e traduzida com ajuda de IA a partir de cada post, e cada sonho tem o link para a fonte.

### Endpoints

- `/` e `/eng`: a página.
- `/status.json`: último sync, resultado e próximo horário.
- `/sync?token=...`: dispara um sync na hora (o token fica na variável `SYNC_TOKEN`).
- `/healthz`: verificação de saúde.

### Rodar localmente

```bash
python3 app/server.py          # http://localhost:8080
SYNC_ON_START=1 python3 app/server.py   # sincroniza ao subir
```

Sem dependências além da biblioteca padrão do Python (e `tzdata`). Os dados de execução ficam em `DATA_DIR` (no Railway, um volume em `/data`).

## Pesquisas

- [`docs/sonhos-shib-lunc.md`](docs/sonhos-shib-lunc.md): todos os sonhos, visões e palavras proféticas sobre Shiba Inu (SHIB) e Terra Luna Classic (LUNC) localizados até 08/10/2026, da base deste projeto e de uma varredura da web (YouTube, X, TikTok, Facebook, Rumble, Patreon, z3news e blogs), com resumo e link de cada fonte. Os de 2026 vêm primeiro.

## Aviso

Os vereditos (cumpriu, falhou) são os que o próprio site ou a lista afirmam. Previsões com prazo ainda aberto ficam sem veredito. Nada aqui é recomendação de investimento.

---

# Prophetic dreams and prices (English)

A page that gathers the dreams, visions and prophetic words published on propheticmoney.com and the Lucas Borin price list, organized as a future events timeline (one line per coin), a dream timeline, deadlines, and a price ladder per coin compared with real market prices. Portuguese at `/`, English at `/eng`. It syncs with the blog every day at midnight New York time, using rules only (no AI). Not investment advice.
