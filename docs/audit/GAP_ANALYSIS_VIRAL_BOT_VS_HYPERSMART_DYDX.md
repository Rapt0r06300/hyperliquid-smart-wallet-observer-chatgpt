# Gap Analysis — Bot viral Claude/Polymarket vs HyperSmart Observer (dYdX v4)

**Date:** 2026-06-11 · **Branche:** `migration-dydx-v4-and-pnl-audit` · **Mode:** PAPER-ONLY, READ-ONLY

> Question: « Que manque-t-il au logiciel (scan, sélection wallets, etc.) pour viser un PnL paper positif comme le bot viral ? »
> Réponse courte: **l'architecture est complète (93/93 tests verts), mais le pipeline n'a jamais tourné sur données réelles.** La base est vide. Le « PnL positif » du commit `d2a54af` provient de wallets démo synthétiques calibrés pour générer des clusters — c'est circulaire, pas une preuve d'edge.

---

## 1. Ce que dit la recherche sur le bot viral Polymarket (juin 2026)

### 1.1 Les claims viraux — à prendre avec recul
- $2 000 → $12 000 en une nuit; $1 → $3,3 M; $1 400 → $238 006 en 11 jours. Aucun de ces chiffres n'est audité; plusieurs analyses pointent du marketing, voire des arnaques (repos GitHub piégés, phishing).
- Réalité on-chain: **92,4 % des wallets Polymarket sont perdants**; 14 des 20 wallets les plus profitables du leaderboard sont des bots.
- La fenêtre d'arbitrage moyenne s'est compressée de 12,3 s (2024) à **2,7 s (2026)**. Un backtest qui fill au mid surestime les retours de **30 à 100 %**.

### 1.2 Ce qui marche vraiment selon les analyses sérieuses
1. **Confluence de signaux, pas copie naïve.** La copie naïve sous-performe le wallet source de **60 à 80 % de son PnL net**. Ce qui marche: attendre que **3+ wallets « known-good » entrent sur le même marché dans une fenêtre courte**, avec assez de profondeur pour fill sans bouger le book.
2. **Le timing de sortie explique l'essentiel de l'écart** (plus que les frais). Suivre les exits du leader est plus important que copier ses entrées.
3. **Sélection stricte des wallets:** ≥50 positions closes, win rate >55 % (mais <90 %, sinon pattern suspect), volume >$100k, ROI positif sur 90+ jours, classement **ajusté du Sharpe** plutôt que ROI brut, stabilité du rang sur plusieurs semaines (filtre « lottery winners »).
4. **Discipline d'exécution:** sizing limité, circuit breakers, semaines de paper avant tout argent réel.

---

## 2. État réel de notre système (vérifié dans le code le 2026-06-11)

### 2.1 Ce qui existe et fonctionne
| Composant viral | Notre équivalent dYdX v4 | État |
|---|---|---|
| Wallet scoring | `scoring.py` (≥10 trades, WR≥40 %, PF≥1.2, 1 trade ≤70 % du PnL) | ✅ codé + testé |
| Edge net après coûts | `edge_calculator.py` (9 composantes de coût, seuil 30bps/3×coûts) | ✅ codé + testé |
| Signaux frais | `signals.py` (rejet >4 s, hard >8 s) | ✅ codé + testé |
| NO_TRADE | `no_trade.py` (raisons tracées) | ✅ codé + testé |
| Lifecycle + orphan closes refusés | `lifecycle.py` | ✅ codé + testé |
| Follow-exit leader | `live_observer.py` `LEADER_EXIT` | ✅ codé |
| Clusters/consensus | `cluster_detector.py` | ✅ codé, **pas câblé comme gate d'entrée** |
| Stop-loss/TP | -1,5 % / +2,5 % fixes | ⚠️ non ajustés à la volatilité |
| Séparation LIVE/BACKTEST/DEMO | `SimulationMode` | ✅ testé |
| Tests | `tests/dydx_v4` | ✅ **93/93 passent** |

### 2.2 Les manques critiques (par ordre d'impact sur le PnL)

**M1 — Aucune donnée réelle n'a jamais traversé le pipeline.** `hypersmart_observer.sqlite3`: 0 wallets, 0 fills, 0 signaux, 0 paper_trades, 2 no_trade_decisions. On ne peut ni prouver ni infirmer un edge sur une base vide. (Note: l'indexer est inaccessible depuis la sandbox Claude — 403 proxy — c'est pourquoi les sessions précédentes ont basculé en démo. Il faut lancer la collecte **sur ta machine**.)

**M2 — Le « PnL positif » actuel est fabriqué.** `wallet_discovery.py::_DEMO_WALLET_SPECS` contient 3 wallets synthétiques dont les positions ont été **éditées exprès** (« BUG FIX: était ETH SHORT → aucun overlap ») pour que le détecteur de clusters trouve des clusters. C'est un test de plomberie, pas un signal. Risque: confondre ce chiffre avec une performance.

**M3 — La découverte ne trouve pas les wallets *profitables*, seulement les wallets *actifs*.** `fast_discover()` scanne les subaccounts Cosmos LCD par solde (≥$500/1000 + positions ouvertes) puis n'enrichit que le **top-5** avec 5 pages de fills. Polymarket a un leaderboard public; dYdX non — il faut le **construire**: énumérer les traders actifs, puis classer **tous** les candidats via `GET /v4/historicalPnl` (déjà implémenté dans `rest_client.get_historical_pnl()` mais **jamais appelé** par la découverte).

**M4 — Seuils de sélection trop laxistes vs standards du bot viral.** Nous: 10 trades, WR≥40 %, PF≥1.2. Bot viral: 50+ trades clos, WR>55 %, 90+ jours d'historique, Sharpe-ranking, re-scoring continu avec rétrogradation automatique. Avec nos seuils, un wallet chanceux sur 2 semaines passe le filtre.

**M5 — Le consensus n'est pas un gate.** La recherche est claire: l'entrée la plus robuste = 2-3+ wallets shortlistés, même marché, même sens, fenêtre de quelques minutes, profondeur suffisante. `cluster_detector.py` existe mais le signal individuel suffit aujourd'hui à ouvrir un paper trade.

**M6 — Sorties non adaptatives.** SL -1,5 % / TP +2,5 % identiques pour BTC et pour un alt 5× plus volatil; pas de trailing stop; pas de time-stop pondéré par le funding (le champ `funding_penalty_bps` existe mais vaut 0 par défaut). Or l'exit timing = 60-80 % de l'écart de copie.

**M7 — Remplissage paper trop optimiste.** Le fill paper doit venir du carnet (`/v4/orderbooks`) au moment du signal: traverser le spread + impact selon la profondeur + latence injectée. Jamais au mid (sinon +30-100 % de PnL fictif).

**M8 — Hygiène repo.** 605 fichiers trackés supprimés du working tree non commités (l'ancien arbre `hyper_smart_observer/*` hors `dydx_v4/`), 20 modifiés, 7 non suivis. Risque de perte de travail et d'historique illisible. À trancher: commit de suppression assumé (Hyperliquid déjà préservé dans `src/hl_observer`) ou restauration.

---

## 3. Plan priorisé pour un PnL paper positif *réaliste*

| # | Action | Module | Effort | Impact PnL |
|---|---|---|---|---|
| 1 | **Lancer la collecte réelle 24/7 sur ta machine** (indexer REST+WS), 2-4 semaines de fills/positions en SQLite | `live_observer`, `indexer` | faible | bloquant pour tout le reste |
| 2 | **Leaderboard builder dYdX**: énumération traders actifs (fills marchés + txs Cosmos) → `historicalPnl` pour chaque candidat → table `wallet_scores` rafraîchie daily (Job A du bot viral) | `wallet_discovery` v2 | moyen | ⭐⭐⭐ |
| 3 | **Durcir la sélection**: ≥50 trades clos, WR>55 %, 90 j d'historique, Sharpe-ranking, max drawdown, re-scoring hebdo + rétrogradation auto | `scoring` | faible | ⭐⭐⭐ |
| 4 | **Consensus gate**: entrée seulement si ≥2 (puis 3) wallets shortlistés convergent <10 min, même marché+sens, profondeur OK | `cluster_detector` → `signals` | faible | ⭐⭐⭐ |
| 5 | **Exits adaptatifs**: SL/TP en multiples d'ATR par marché, trailing stop, time-stop funding-aware; `LEADER_EXIT` reste prioritaire | `live_observer`, `paper` | moyen | ⭐⭐⭐ |
| 6 | **Fills honnêtes**: orderbook au signal, spread traversé, slippage par profondeur, latence simulée; tag `data_source` (real/demo) sur chaque trade; PnL démo banni du dashboard live | `paper`, `edge_calculator` | moyen | ⭐⭐ (évite faux positifs) |
| 7 | **Mesure anti-illusion**: walk-forward, out-of-sample, tracking « notre PnL vs PnL du leader sur les mêmes trades » (copy capture ratio), rapport NO_TRADE hebdo | `backtest` | moyen | ⭐⭐ |
| 8 | Commit/restauration des 605 suppressions + tag de sauvegarde | git | faible | hygiène |

### Attentes réalistes
Même un bon copy-bot capture historiquement **20-40 % du PnL du wallet source**. Les chiffres viraux ($1 → $3,3 M) sont invérifiables et l'écosystème qui les promeut contient des arnaques documentées. Notre objectif reste celui du projet: **moins de trades, plus propres** — un PnL paper positif modeste et reproductible après coûts vaut mieux qu'un gros chiffre démo. Aucun PnL positif n'est promis.

---

## 4. Sécurité (inchangé)
READ-ONLY, PAPER-ONLY, TESTNET-FIRST, DENY-BY-DEFAULT. 0 ordre réel, 0 argent réel, 0 clé privée, 0 signature, 0 dépôt/retrait. Toutes les actions ci-dessus n'utilisent que les endpoints publics de l'Indexer/LCD.

## 5. Sources
- [Finbold — Claude turns $2,000 to $12,000 overnight on Polymarket](https://finbold.com/claude-turns-2000-to-12000-overnight-on-polymarket-here-is-how/)
- [Turbine — A Claude-Powered Bot Turned $1 into $3.3M on Polymarket](https://www.turbinefi.com/blog/polymarket-ai-bot-1-to-3-million)
- [Medium — Why 95% of people copying the $1M Polymarket bot still go broke](https://medium.com/@davidvincent2010/why-95-of-people-copying-the-1m-polymarket-bot-still-go-broke-and-what-the-5-do-differently-43f95084f34e)
- [Gate News — Claude AI Trading Bot Goes Viral: Polymarket Arbitrage Strategy Exposed](https://www.gate.com/news/detail/claude-ai-trading-bot-goes-viral-polymarket-arbitrage-strategy-exposed-some-19541646)
- [QuantVPS — Polymarket Copy Trading Bot: How Traders Find Alpha](https://www.quantvps.com/blog/polymarket-copy-trading-bot)
- [Medium — Top Polymarket Wallets: How to Find Best Traders for Copy Trading](https://medium.com/@gemQueenx/top-polymarket-wallets-how-to-find-best-traders-for-copy-trading-26704fdfd836)
- [Scand.ai — Polymarket Claude AI Arbitrage Bot Controversy (scam concerns)](https://scand.ai/scandal/polymarket-claude-ai-arbitrage-bot-controversy)
- [Hacker News — I ran an arbitrage bot on Polymarket. Here are the real numbers](https://news.ycombinator.com/item?id=48461522)
- [BeInCrypto — Traders Use Claude AI to Build Polymarket Bots](https://beincrypto.com/claude-ai-polymarket-trading-bots-millions/)
- [Stuart Glover — Claude AI Trading Bot Claims Face Skepticism](https://stuartglover.com/claude-ai-trading-bot-claims-on-polymarket-face-skepticism-what-we-know/)
