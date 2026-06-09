# MEGA V1 Internet Intelligence Report

Date: 2026-06-02

Ce rapport separe les faits fiables des claims commerciaux/OSINT. Il ne sert pas a
promettre un profit; il sert a transformer les informations utiles en garde-fous,
tests et logique locale.

## Sources consultees

1. Hyperliquid Docs - WebSocket subscriptions
   - URL: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions
   - Fiabilite: OFFICIAL_HYPERLIQUID
   - Finding: les messages `userFills` et `userFundings` commencent par un snapshot
     `isSnapshot: true`; les updates suivantes sont `isSnapshot: false`.
   - Decision: le scanner WS doit dedupliquer les snapshots et ne pas les compter
     comme opportunites fraiches sans contexte.

2. Hyperliquid Docs - WebSocket
   - URL: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket
   - Fiabilite: OFFICIAL_HYPERLIQUID
   - Finding: les clients doivent gerer les deconnexions et reconnecter proprement;
     les donnees manquees doivent etre recuperees via snapshot ou requete info.
   - Decision: le temps reel ne doit pas etre une boucle infinie fragile; il faut
     `realtime-health`, replay local et fallback info read-only.

3. Hyperliquid Docs - Rate limits and user limits
   - URL: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
   - Fiabilite: OFFICIAL_HYPERLIQUID
   - Finding: REST weight limite a 1200/min/IP; `userFills` et
     `userFillsByTime` ajoutent du poids par 20 elements; Explorer weight 40;
     WebSocket limite a 10 connexions, 30 nouvelles connexions/min, 1000
     subscriptions, 10 users uniques.
   - Decision: scanner massif = local/index/historique; reseau = shortlist bornee.

4. Hyperliquid Docs - Info endpoint
   - URL: https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint
   - Fiabilite: OFFICIAL_HYPERLIQUID
   - Finding: `userFills` retourne les fills recents; les fills contiennent
     `dir`, `startPosition`, `closedPnl`, `fee`, `tid`, `oid`, `hash`.
   - Decision: classification open/add/reduce/close doit privilegier fills +
     position, et marquer UNKNOWN si contradiction.

5. Baselight - Hyperliquid Node Fills By Block
   - URL: https://baselight.app/u/hyperliquid/dataset/node_fills
   - Fiabilite: DATA_PROVIDER
   - Finding: l'historique complet de fills peut etre analyse hors API runtime,
     avec timestamps, start_position, dir, closed_pnl, fees, taker/maker.
   - Decision: pour "scanner des milliers de wallets", il faut importer/indexer
     un dataset local, pas spammer `/info`.

6. Wallet Hunter / Polymarket "Claude-powered" claims
   - URL: https://wallethunter.space/
   - Fiabilite: OSINT_CLAIM / COMMERCIAL_CLAIM
   - Finding: claims de scan 14k wallets, top wallets, sharpe, copy live.
   - Decision: utilisable comme inspiration UX/architecture, pas comme preuve de
     rentabilite. HyperSmart doit afficher "research only" et analyser les pertes.

7. Polymarket wallet/copy tools et discussions publiques
   - Exemples: PolyMart, PolymarketWallets, Reddit.
   - Fiabilite: OSINT_CLAIM / COMMERCIAL_CLAIM / USER_REPORT
   - Finding: les themes repetes sont leaderboard, winrate, timing, consensus de
     plusieurs wallets, mais aussi retard, hedges invisibles, survivorship bias.
   - Decision: consensus seul ne suffit pas; edge_remaining, couts, retard,
     liquidite et no-trade restent obligatoires.

## Conclusion produit

Le "bot magique" reproductible de facon responsable n'est pas un bouton profit. La
partie credible est:

- index local massif;
- shortlist;
- flux read-only borne;
- deltas open/add/reduce/close;
- edge_remaining apres couts;
- refus explicites;
- simulation 1000 fictifs;
- logs pertes/root-cause;
- dashboard simple et vrai.

