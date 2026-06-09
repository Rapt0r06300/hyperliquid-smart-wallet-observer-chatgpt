# Limites connues — dYdX v4

## Limites de l'Indexer public

1. **Pas de leaderboard natif** — contrairement à Hyperliquid, dYdX v4 n'a pas
   d'endpoint public listant les meilleurs traders. Il faut constituer la liste
   de wallets observés manuellement ou via un autre source de données.

2. **Rate limit REST** — environ 10 req/s sur testnet. Le client est configuré
   à 5 req/s par défaut.

3. **Fills paginations** — limitées à 100 fills par page. Un backfill complet
   d'un compte actif peut nécessiter plusieurs dizaines de pages.

4. **Délai WebSocket** — les messages WS peuvent avoir 100-500ms de latence
   supplémentaire vs l'exécution réelle sur chaîne.

5. **Données historiques limitées** — l'Indexer testnet ne conserve pas
   l'historique indéfiniment. Pour les backtests, utiliser des données
   exportées et stockées localement.

## Limites du système de copie

1. **Délai de copie incompressible** — entre la détection d'un fill et
   l'hypothétique ordre de copie (testnet/simulation uniquement), il y a
   au minimum 300ms de latence réseau + traitement. Le modèle utilise
   `delay_ms=300_000` (5 min) dans les backtests pour être conservateur.

2. **Edge réel après coûts** — l'edge disponible après frais (5 bps taker ×2),
   spread (3 bps), slippage (5 bps), latence (2 bps), dégradation copie (5 bps)
   = 20 bps de coûts totaux. Le signal doit avoir `edge_remaining > 30 bps`
   pour être accepté.

3. **Qualité des smart wallets** — sur dYdX v4, les "smart wallets" peuvent
   simplement être des bots eux-mêmes. Le scoring (winrate ≥40%, profit_factor
   ≥1.2, ≥10 trades) filtre les chanceux.

## Limites du module actuel (Phase 1)

- Pas encore de vraie liste de smart wallets identifiés sur dYdX v4
- Le WebSocket n'est pas connecté en continu (démarrage manuel requis)
- Pas d'interface commune avec Hyperliquid (modules indépendants)
- Backfill limité au testnet (données peu représentatives du mainnet)

## Ce qui ne changera jamais

- Aucun ordre réel ne sera jamais émis
- Aucune clé privée ne sera jamais utilisée
- Le PnL paper n'est jamais présenté comme un PnL réel
