# HyperSmart - Synthese recherche "magic bot" et logique reproducible

Date: 2026-06-01

Ce document separe les promesses marketing des mecanismes techniques que HyperSmart peut reproduire en simulation locale, sans ordre reel.

## Sources consultees

- Hyperliquid docs - `/info` endpoint read-only: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- Hyperliquid docs - WebSocket subscriptions: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions
- Hyperliquid docs - rate limits and user limits: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
- Polymarket copy bot public page: https://roswelly.github.io/polymarket-copy-trading-bot/
- PolyGold public copy-trading page: https://www.polygold.trade/
- PolyTraderBot public copy bot page: https://www.polytraderbot.com/copy-trading.html
- Polycopy public copy-trading page: https://polycopy.app/
- Remote OpenClaw article on Claude + Polymarket bot architecture: https://www.remoteopenclaw.com/blog/how-to-build-a-polymarket-copy-trading-bot-with-claude
- Reddit/Polymarket discussions used only as weak signals: latency, state persistence, private-key risk and edge decay are recurring concerns.
- Polymarket copy-trading product pages and GitHub search results, utilises uniquement comme inspiration d'architecture, pas comme preuve de profit.
- GitHub search: projets Hyperliquid/Polymarket copy-trading publics, dont `ssanin82/hyperliquid-copy-trader` et `Parallax-Trading/polymarket-copy-trading-bot`.

## Ce qui revient dans les bots Polymarket/Hyperliquid credibles

1. Une liste de leaders est construite hors du hot path.
2. Le bot surveille peu de leaders avec forte fraicheur, plutot que scanner tous les wallets user-specific.
3. La copie est proportionnelle au capital, avec caps stricts.
4. La latence, les frais, le spread et le slippage degradent l'edge.
5. Une position ouverte par un leader n'est pas une preuve suffisante: il faut contexte, repetition, liquidite et risque.
6. Le consensus multi-wallet est utile seulement si les wallets sont deja qualifies et si l'action est quasi simultanee.
7. Les sorties doivent suivre les reductions/fermetures du ou des leaders observes; fermer uniquement parce que le PnL local est rouge invente une strategie.
8. Les promesses de profit garanti sont a rejeter: les meilleures pages publiques elles-memes reconnaissent que la performance passee ne garantit rien.

## Logique Polymarket transposable a HyperSmart

Les pages publiques Polymarket convergent sur une logique tres precise:

1. `Discover`: construire une base de leaders depuis leaderboard, activite recente et historique verifie.
2. `Qualify`: refuser les wallets qui n'ont qu'un gros gain, peu d'historique, une forte concentration PnL ou une categorie trop etroite.
3. `Watch`: suivre les achats/ventes en temps reel avec un curseur persistant, jamais en relisant toute l'histoire a chaque boucle.
4. `Dedupe`: stocker les derniers trade ids/fill ids pour ne jamais rejouer deux fois le meme evenement.
5. `Size`: calculer une taille proportionnelle au capital local avec plafond par marche/coin et plafond global.
6. `Gate`: refuser si le prix a deja bouge, si la liquidite manque, si le spread est trop large, si le signal est trop vieux.
7. `Exit`: suivre la sortie du leader seulement si la position locale correspond bien a l'entree copiee.
8. `Report`: afficher les refus autant que les entrees, car les no-trades expliquent si le bot est trop strict, trop lent ou mal alimente.

Pour Hyperliquid, cela devient:

- public trades WebSocket pour decouvrir rapidement beaucoup de wallets sans user-specific abuse;
- shortlist reduite pour `userFills` read-only, car Hyperliquid limite les users uniques en WebSocket;
- consensus multi-wallet uniquement sur coin + sens + fenetre courte;
- `edge_remaining_bps` obligatoire apres frais, spread, slippage, latence, degradation, liquidite et crowding;
- journal de session persistant jusqu'a fermeture du lanceur;
- aucune promesse de gain et aucune execution.

## Ce que Claude/LLM ne doit pas faire dans HyperSmart

Un LLM peut aider a ecrire du code, documenter ou analyser des rapports hors ligne. Il ne doit pas etre dans la boucle chaude:

- pas de decision d'entree/sortie live par LLM;
- pas de parsing fragile d'une page web par prompt;
- pas de transformation d'une phrase en ordre;
- pas de gestion de cle privee;
- pas d'execution testnet/mainnet.

La boucle chaude doit rester deterministe, testee et auditable: source event -> delta -> signal candidate -> edge remaining -> risk gate -> simulation locale ou no-trade.

## Adaptation HyperSmart en simulation

Le mode simulation HyperSmart applique maintenant:

- scan public read-only des trades par coin pour decouvrir des wallets actifs;
- promotion des wallets actifs vers une shortlist bornee;
- surveillance `userFills` WebSocket read-only sur les slots disponibles;
- exclusion des snapshots historiques pour ne pas simuler de vieux trades;
- rejet des fills trop vieux;
- detection OPEN/ADD/REDUCE/CLOSE;
- score `edge_remaining_bps` obligatoire;
- position locale virtuelle seulement si frais, spread, slippage, latence, liquidite et consensus restent acceptables;
- position de consensus: plusieurs leaders meme coin + meme sens dans la fenetre fraiche ouvrent une seule position locale partagee, pas N positions dupliquees;
- fermeture/reduction de consensus: seules les fermetures/reductions des leaders qui ont contribue au cluster peuvent reduire cette position;
- PnL de session persistant dans `data/runtime/ui_simulation_state.json` jusqu'a fermeture/reinitialisation du lanceur.

## Limites volontaires

- Aucun scraping agressif de l'explorer Hyperliquid.
- Aucun contournement de limites.
- Aucun endpoint `/exchange`.
- Aucune signature.
- Aucune cle privee.
- Aucun ordre reel.
- Aucun testnet executor actif.
- Aucun LLM dans le hot path de decision.
- Aucun affichage de profit garanti.

## Prochaine amelioration utile

Le prochain gain de qualite doit porter sur le classement des leaders:

- calculer la performance recente vs historique;
- penaliser les wallets mono-trade ou one-big-win;
- mesurer la degradation de copie apres latence;
- enrichir la liquidite par BBO/L2Book read-only;
- conserver un journal no-trade explicite pour chaque opportunite rejetee.
