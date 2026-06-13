# Le « bot viral de Claude » — méthode réelle confirmée + adaptation dYdX

Recherche web, 2026-06-12. Sources en bas. READ-ONLY / PAPER-ONLY.

L'utilisateur a précisé : le bot viral **original** tourne sur **Polymarket**, et
on veut l'adapter à **dYdX**. Voici ce que ce bot fait *vraiment*, et ce qui est
transposable (ou pas) à un perp DEX.

---

## 1. Le bot viral original — Polymarket (cas Mary Evan, avril 2026)

Claude a servi à construire un **terminal de monitoring** Polymarket. D'après la
créatrice, le bot :
1. **scanne Polymarket pour les marchés mal-pricés** (mispricing),
2. **extrait des opportunités d'arbitrage**,
3. **trace les wallets qui copient ces stratégies**, et
4. **copie-trade les wallets trouvés** (via un bot Telegram), en
   **« s'améliorant à chaque wallet découvert »**.

Citation : *« Claude a créé un terminal de monitoring et a copy-tradé les wallets
trouvés… c'est un agent IA qui s'améliore à chaque wallet découvert. »*

### Les stratégies réelles (recoupées sur plusieurs sources)

| Stratégie | Mécanisme | Transposable à dYdX ? |
|-----------|-----------|------------------------|
| **Arbitrage de latence** | Les contrats crypto court terme de Polymarket (BTC up/down 5–15 min) **se repricent plus lentement** que le spot Binance/Coinbase → acheter le côté quasi-certain avant que Polymarket rattrape. | ❌ **Non** tel quel. dYdX est un CLOB on-chain qui reprice en temps réel ; pas de « marché lent » à arbitrer contre le spot. |
| **Mispricing de probabilité** | Claude estime la vraie probabilité d'un événement vs prix implicite Polymarket → parier l'écart. | ⚠️ **Partiel.** Pas d'« événement » sur un perp ; l'analogue est l'**edge net après coûts** d'un trade directionnel. |
| **Copy de smart-money** | Tracer et copier les wallets gagnants, set qui grandit en continu. | ✅ **Oui, pleinement.** C'est le cœur réutilisable. |
| **Modèles prédictifs** | Ex. modèle NBA entraîné sur 3 ans de données → mispricing sportif. | ❌ Hors-scope (spécifique aux marchés d'événements). |

### Chiffres cités (à prendre avec recul)
- Edge **$2–$20 par trade**, mais **haute fréquence** → ça s'accumule.
- Un bot a scanné **1 000+ wallets** ; une adresse $120 → $1,4 M sur 1 947 trades, **55 % winrate**.
- **Mais** : à mesure que les bots se multiplient, les fenêtres se referment et
  l'edge se dégrade. Des configs erronées ont causé de **grosses pertes**. Des
  soupçons d'arnaque entourent certaines démos.

---

## 2. La variante Hyperliquid (copy-trading, cas Gencay, mai 2026)

Plus proche de notre projet. **3 jobs découplés** :
- **Job A** (1×/jour) : pull leaderboard Hyperliquid → **filtre le bruit** → **classe
  par qualité d'exécution** → écrit une shortlist JSON.
- **Job B** (toutes les 5 min) : lit la shortlist → fetch positions ouvertes de
  chaque wallet → **diff vs snapshot précédent** → nouvelle position = **BUY**,
  position fermée = **SELL** → applique au portefeuille **paper** ($10 000).
- **Job C** (toutes les 30 min) : lit l'état → PnL 24h → ping Slack (read-only).

Point clé : *« sur un perp DEX comme Hyperliquid, chaque position et chaque fill
est on-chain, gratuit à interroger, sans clé API. »* Claude = **couche d'analyse/
sélection** (edge vs chance, filtrage), **pas** la couche d'exécution.

---

## 3. Adaptation à dYdX v4 — ce qu'on garde

Le perp DEX n'a pas de « marché lent » à arbitrer. Ce qui transfère, c'est le
**triptyque smart-money** :

1. **Découvrir un maximum de wallets** (« s'améliorer à chaque wallet trouvé »)
   → `wallet_harvester.py` : agrège leaderboard + flux de trades + on-chain +
   datasets, déduplique dans un index, score, classe. Voir
   `docs/migration/DYDX_V4_WALLET_HARVESTER.md`.

2. **Capturer le move vite** (l'analogue de l'« arbitrage de latence » : plus on
   détecte tôt le move d'un wallet, plus on capture son edge avant qu'il se
   dégrade) → `fast_scanner.py` (WebSocket temps réel, < 1 s vs 8–58 s avant).
   Voir `docs/migration/DYDX_V4_FAST_SCANNER.md`.

3. **Ne copier que quand l'edge net est positif** (l'analogue du « mispricing » :
   on ne suit que si edge − frais − spread − slippage − latence − dégradation de
   copie > seuil, et si plusieurs smart-wallets convergent) → `consensus.py`,
   `edge_calculator.py`, `no_trade.py` (déjà en place).

### Comment obtenir « le maximum de wallets » sur dYdX

- **Pas de scraping HTML** : le frontend lit la même donnée que nous ; scraper le
  site serait plus lent, fragile et contraire aux ToS. Inutile.
- **Source haute couverture** : les données dYdX v4 sont **on-chain** (appchain
  Cosmos). L'Indexer REST exige de connaître l'adresse à l'avance (pas de « liste
  toutes les adresses »). Pour énumérer, on lit les **transactions committées**
  (full node / RPC) — chaque ordre/fill porte l'adresse de l'expéditeur — et/ou
  on consomme le **flux de trades par marché**. C'est ainsi que Hyperbot indexe
  600k+ adresses et HyperTracker 1,5 M.
- **Nuance dYdX** : le canal Indexer `v4_trades` est anonymisé (pas d'adresse) ;
  la couche **on-chain** est la vraie source d'adresses. Le projet a déjà un
  `cosmos_client.py` (LCD) pour ça — le harvester s'appuie dessus comme une source.

---

## 4. Réalité honnête (ne jamais maquiller)

- Les captures virales sont du **biais du survivant** : « 92,4 % des wallets
  Polymarket perdent de l'argent » ; pour chaque screenshot $1k→$14k, des
  centaines de bots ont perdu en silence.
- Avoir **plus de wallets** n'augmente pas le PnL par magie : ça **élargit le
  vivier de candidats** pour que les filtres (consensus, edge net, liquidité) aient
  de la matière première de qualité. Le profit vient du **filtrage**, pas du volume.
- On ne promet aucun PnL positif. On maximise la *probabilité* d'un PnL paper
  réaliste en réduisant les erreurs (signaux vieux, wallets perdants, coûts).

---

## Sources
- [I Built a Claude Trading Bot That Copies Hyperliquid Millionaires (Gencay)](https://www.learnwithmeai.com/p/claude-trading-bot-hyperliquid)
- [Claude turns $2,000 to $12,000 overnight on Polymarket (Finbold)](https://finbold.com/claude-turns-2000-to-12000-overnight-on-polymarket-here-is-how/)
- [Claude AI Trading Bot Goes Viral: Polymarket Arbitrage Strategy Exposed (Gate)](https://www.gate.com/news/detail/claude-ai-trading-bot-goes-viral-polymarket-arbitrage-strategy-exposed-some-19541646)
- [Claude AI-powered arbitrage bot turns $600 into $10,000 in 48 hours (Finbold)](https://finbold.com/claude-ai-powered-arbitrage-bot-turns-600-into-10000-in-48-hours/)
- [Hyperbot — Whale Tracker + Copy Trading (600k+ adresses)](https://hyperbot.network/)
- [HyperTracker — Real-Time Wallet Tracking (1.5M wallets)](https://hypertracker.io/)
- [dYdX v4 Indexer Client docs](https://docs.dydx.exchange/api_integration-clients/indexer_client)
