# Bot Viral Claude/Polymarket vs HyperSmart Observer — Comparaison & Adaptation

## 1. Qu'est-ce que le "bot viral" ?

Le phénomène viral de 2025-2026 repose sur plusieurs variantes de bots Claude/AI opérant sur Polymarket :

**Variante A — Copy Trading (LearnWithMeAI / Hyperliquid)**
- Job A (daily) : Pull le leaderboard, filtre le bruit, rank par qualité d'exécution → shortlist JSON
- Job B (5min) : Lit la shortlist, fetch positions ouvertes, compare au snapshot précédent → signaux BUY/SELL
- Job C (30min) : Calcule PnL 24h, envoie pulse Slack
- Paper portfolio $10,000 d'abord, jamais d'argent réel sans validation

**Variante B — AI Analysis (RobotTraders / ClaudePolymarketTrader)**
- Price Scanner (15s) : Fetch marchés actifs, filtre par horizon (<72h), calcule momentum/volatilité/volume
- Claude Brain (30s) : Envoie data marché + état portfolio + historique → JSON structuré (decision/confidence/reasoning)
- Signal Validation : Edge minimum, confidence, position limits, risk thresholds
- Order Executor : CLOB Fill-or-Kill, fallback Good-til-Cancelled
- Exit System (15s) : Take-profit, stop-loss, trailing stop, time stop, breakeven
- Circuit Breaker : Pause si drawdown/streak/PnL dépasse seuils

**Variante C — Whale Mirroring (QuickNode / QuantVPS)**
- Watch : Monitor wallet addresses on-chain via WebSocket + REST polling
- Decode : Parse transaction → market, direction (YES/NO), size, price
- Mirror : Sizing proportionnel, risk filters, copy order
- Scoring wallets : PnL réalisé, win-rate, Sharpe, drawdown, diversité, consistance (refresh 60s)
- Filtre wallets : 50+ positions closes min, win rate >55%, volume >$100k, ROI positif 90+ jours

**Variante D — Production (Chudi.dev / Polyphemus)**
- 36,000 lignes de code, Kelly Criterion sizing
- Five-module : signal gen (Binance WS), position management (SQLite), exit strategies, state persistence, health monitoring
- Two-gate verification : Gate 1 automated (type checks, linting, tests), Gate 2 manual (6-question checklist)
- 6 semaines de paper trading avant argent réel

## 2. Composants communs à tous les bots viraux

| Composant | Rôle | Notre équivalent HyperSmart |
|-----------|------|-----------------------------|
| Leaderboard Scanner | Découverte wallets profitables | `wallets/leaderboard_*.py` + `top_wallet_ranker.py` |
| Wallet Scorer | Score multi-critères (win rate, PF, drawdown, consistency) | `wallets/scoring.py` + `wallets/skill_vs_luck.py` |
| Position Delta Engine | Détection changements positions (OPEN/CLOSE) | `wallets/position_delta_engine.py` + `wallets/snapshot_engine.py` |
| Signal Detector | Convertir deltas en signaux copyables | `copying/signal_detector.py` |
| Edge Calculator | Calculer l'edge net après coûts | `edge/edge_remaining.py` + `edge/copy_degradation.py` |
| Risk Scoring | Score de risque du signal (liquidité, spread, slippage) | `copying/realtime_magic_score.py` |
| Consensus Engine | Cluster multi-wallets même coin/direction | `clusters/wallet_clusterer.py` + `copying/consensus_leader_selector.py` |
| Paper Simulator | Positions virtuelles, PnL sans argent réel | `ui/routes.py` (paper engine) |
| Circuit Breaker | Stop trading si drawdown/streak dépasse seuils | `risk/risk_engine.py` + loss cooldowns |
| Exit Engine | TP/SL/trailing/time-based exits | `exits/exit_engine.py` + `exits/leader_exit_monitor.py` |
| Dashboard | Visualisation PnL, positions, wallets | `ui/` (Flask + templates) |
| Safety Guard | Aucun ordre réel possible | `execution/live_executor_disabled.py` |

## 3. Ce que notre système fait déjà (273 fichiers Python)

### Leaderboard Discovery (Job A du bot viral)
- `wallets/leaderboard_*.py` : 10+ fichiers de scraping/parsing/validation du leaderboard
- `wallets/top_wallet_ranker.py` : Classement multi-critères
- `wallets/discovery.py` + `discovery_scoring.py` : Découverte et scoring de wallets
- `copying/leaderboard_autoselect.py` : Sélection automatique des leaders (top_n=50, min_score=60, min_consistency=55, max_drawdown=35%)

### Position Monitoring (Job B du bot viral)
- `wallets/position_delta_engine.py` : Détection des changements de position
- `wallets/snapshot_engine.py` + `snapshot_service.py` : Snapshots réguliers
- `wallets/user_fills_live.py` : Fills en temps réel
- `wallets/public_trades_live.py` : Trades publics en temps réel

### Signal Pipeline (Claude Brain / Edge Calculator)
- `copying/signal_detector.py` : Pipeline complète delta → signal → score → risk → decision
- `copying/realtime_magic_score.py` : Scoring temps réel avec copy_degradation model
- `edge/edge_remaining.py` : Calcul edge = gross_edge - all_costs
- `edge/copy_degradation.py` : fee + spread + slippage + latency + adverse_selection
- `edge/signal_decay.py` : Decay temporel des signaux
- `edge/cost_validation.py` : Validation edge minimum

### Wallet Quality (Scoring multi-dimensionnel)
- `wallets/scoring.py` : Win rate (30%) + PF (20%) + PnL (15%) + sample (15%) + activity (10%) + Sharpe bonus
- `wallets/skill_vs_luck.py` : Détection skill vs chance
- `wallets/toxicity.py` : Détection wallets toxiques
- `analysis/methodology_profiler.py` : Profiling du style de trading

### Risk Management
- `risk/risk_engine.py` : Moteur de risque
- `copying/realtime_magic_score.py` : Circuit breaker via loss cooldowns, exposure caps, edge gates
- `exits/exit_engine.py` : Exits multi-mode
- Safeguards: `MAX_OPEN_PAPER_TRADES_REACHED`, `MAX_TOTAL_EXPOSURE_CAP_ACTIVE`, `LIQUIDITY_TOO_LOW`

### Scanner Optimization (pour dYdX v4)
- `scanner/fresh_scan_strategy.py` : Cycles 6s, 200 WS subs/256, gap recovery
- `scanner/throughput_planner.py` : Rate limit safe, rotation automatique
- `scanner/scanner_models.py` : Budget de scan 200 leaders/run

### Dashboard & Reporting
- `ui/routes.py` : ~3400+ lignes, Flask, API complète
- `ui/templates/index.html` + `ui/static/app.js` : Dashboard live
- Dashboard dYdX panel séparé, simulation overview

### Safety (règle absolue)
- `execution/live_executor_disabled.py` : `place_order` lève toujours `LiveExecutionDisabled`
- `simulation/modes.py` : Séparation LIVE/BACKTEST/REPLAY/TEST_FIXTURE
- Aucune clé privée, aucun seed, aucun wallet connect, aucun appel d'API privée

## 4. Ce qui manque / peut être amélioré

### 4a. Wallet Scoring : aligner sur les critères Polymarket pro

Les bots viraux performants utilisent ces critères pour filtrer les wallets :
- **200+ resolved trades** sur 24 mois (nous: min 20 trades → devrait être plus strict)
- **Win rate >55%** (nous: pas de seuil minimum strict, score graduel)
- **Diversité : au moins 3 marchés/catégories** (nous: pas encore implémenté)
- **ROI positif sur 90+ jours** (nous: juste `require_positive_pnl`)
- **Activité récente** (trades dans les 90 derniers jours, nous: `active_days` basique)
- **Red flags** : win rate >95% = suspect, changement brusque de style (nous: `toxicity.py` mais pas assez granulaire)

### 4b. Signal Freshness : tighter pour copy trading

Les meilleurs bots copient en <15 secondes. Notre `max_signal_age_ms = 120_000` (2 min) est trop laxiste pour du copy trading temps réel.

### 4c. Execution Speed Metrics

Les bots viraux mesurent le "time to copy" (détection → exécution simulée). Nous ne le trackons pas explicitement.

### 4d. PnL Attribution par Leader

Les meilleurs bots trackent le PnL par leader copié pour identifier qui contribue positivement et éjecter les leaders qui sous-performent. Notre système agrège.

### 4e. Dynamic Leader Rotation

Le bot de LearnWithMeAI recompute la shortlist daily. Notre `leaderboard_autoselect.py` le fait mais sans rotation automatique basée sur performance récente.

## 5. Mapping des concepts Polymarket → dYdX v4

| Polymarket | dYdX v4 | Notre implémentation |
|------------|---------|----------------------|
| Wallet address (Polygon) | Account + Subaccount (Cosmos) | `dydx_v4/models.py` normalized |
| YES/NO tokens (CLOB) | LONG/SHORT perpetuals | `OPEN_LONG/OPEN_SHORT/CLOSE_*` |
| Gamma API (markets) | Indexer REST `/v4/markets` | `dydx_v4/rest_client.py` |
| CLOB orderbook | dYdX orderbook | Indexer REST + WS |
| Polygon WebSocket | Indexer WebSocket v4_accounts | `dydx_v4/ws_client.py` |
| Market resolution | Position P&L (mark vs entry) | `ui/routes.py` paper engine |
| 0-2% fees | 2.5-5 bps taker | `cost_bps = 5.0` |

## 6. Sécurité — Confirmation

**0 ordre réel, 0 argent réel, 0 clé privée, 0 signature, 0 dépôt/retrait.**

- `live_executor_disabled.py` : Toute tentative d'ordre lève une exception
- `simulation/modes.py` : LIVE/BACKTEST/REPLAY/TEST_FIXTURE strictement séparés
- Aucun `py-clob-client`, aucun `place_order` fonctionnel
- Dashboard en lecture seule
- Paper trades = entrées SQLite virtuelles, pas de transactions blockchain

## Sources de recherche

- [Claude turns $2,000 to $12,000 overnight on Polymarket](https://finbold.com/claude-turns-2000-to-12000-overnight-on-polymarket-here-is-how/)
- [Claude AI Trading Bots Are Making Hundreds of Thousands on Polymarket](https://medium.com/@weare1010/claude-ai-trading-bots-are-making-hundreds-of-thousands-on-polymarket-2840efb9f2cd)
- [I Built a Claude Trading Bot That Copies Hyperliquid Millionaires](https://www.learnwithmeai.com/p/claude-trading-bot-hyperliquid)
- [Polymarket Bot That Asks Claude to Analyse and Trade](https://robottraders.io/blog/polymarket-ai-bot-claude-python)
- [Polymarket Copy Trading Bot: How Traders Find Alpha](https://www.quantvps.com/blog/polymarket-copy-trading-bot)
- [Building a Polymarket Copy Trading Bot (QuickNode)](https://www.quicknode.com/guides/defi/polymarket-copy-trading-bot)
- [How I Built a Claude Code Trading Bot: 36,000 Lines](https://chudi.dev/blog/claude-code-production-trading-bot)
- [ClaudePolymarketTrader (GitHub)](https://github.com/Willy196616/ClaudePolymarketTrader)
- [Polymarket Agents Official (GitHub)](https://github.com/Polymarket/agents/)
- [CloddsBot (GitHub)](https://github.com/alsk1992/CloddsBot)
- [Traders Use Claude AI to Build Polymarket Bots](https://beincrypto.com/claude-ai-polymarket-trading-bots-millions/)
