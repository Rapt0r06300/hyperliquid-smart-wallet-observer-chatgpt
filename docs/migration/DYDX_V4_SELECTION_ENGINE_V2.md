# Selection Engine v2 — dYdX v4 (standards bot viral)

**Date:** 2026-06-11 · **Statut:** implémenté, 137/137 tests verts · **Mode:** PAPER-ONLY / READ-ONLY

Réponse au gap analysis `docs/audit/GAP_ANALYSIS_VIRAL_BOT_VS_HYPERSMART_DYDX.md`.
Objectif: maximiser la probabilité d'un PnL paper positif RÉEL (jamais inventé,
jamais garanti). Moins de trades, plus propres.

## Nouveaux modules (`hyper_smart_observer/dydx_v4/`)

| Module | Rôle | Point clé |
|---|---|---|
| `selection.py` | Tiers stricts ELITE/STANDARD/WATCH/REJECTED | ELITE: ≥50 trades, WR≥55%, PF≥1.5, Sharpe≥1.0, ≥60j, DD≤25%, concentration≤50%. WR>90% = suspect → WATCH. Données démo → JAMAIS copiable. Promotion 1 tier/refresh, rétrogradation immédiate. |
| `leaderboard.py` | Leaderboard dYdX (inexistant nativement) | Énumération (Cosmos scan + base) → `/v4/historicalPnl` + fills pour CHAQUE candidat → Sharpe/DD/ancienneté → classement composite → persistance SQLite `dydx_leaderboard` → promotions/démotions entre runs → export shortlist JSON. |
| `consensus.py` | Confluence multi-wallets | Entrée valide seulement si ≥2 comptes shortlistés ouvrent même marché+sens en <10 min. CLOSE/REDUCE jamais bloqués. Câblé dans `DydxSignalEngine` (raison `CONSENSUS_NOT_REACHED`). |
| `adaptive_exits.py` | Exits ATR | SL=1.5×ATR, TP=3×ATR, trailing 1×ATR (armé après +1×ATR), time-stop 48h (÷2 si funding adverse >0.01%/h). Fallback % fixes préservé si pas de candles. |
| `fill_simulator.py` | Fills honnêtes | Jamais au mid: VWAP en marchant le carnet réel, spread traversé, max 10% de la profondeur sinon REFUS, pénalité latence. `data_source` ∈ {REAL_INDEXER, DEMO_SYNTHETIC, FALLBACK_ESTIMATED} sur chaque trade. |
| `metrics.py` | Anti-illusion | Copy capture ratio (notre PnL vs leader sur trades appariés), walk-forward par fenêtres, résumé NO_TRADE hebdo. |

## Intégrations
- `signals.py`: gate consensus (6b) si tracker fourni + `consensus_required=True`.
- `live_observer.py`: Gate 8 fill honnête (refus si profondeur insuffisante),
  plan d'exit ATR par position, trailing+time-stop dans `_check_exits`,
  compteurs `entry_fills_{real,fallback,demo}` et flag `demo_data` dans stats.
- `config.py`: bloc "Sélection v2 / consensus", "Exits adaptatifs", "Fills honnêtes"
  (surchargables par env: `DYDX_CONSENSUS_*`).
- `cli.py`: commande `leaderboard` (`--max-candidates`, `--scan-pages`, `--export`).
- `models.py`: `CONSENSUS_NOT_REACHED`, `INSUFFICIENT_DEPTH`.

## Lancement sur ta machine (collecte réelle 24/7)
```bash
cd "Projet invest"
python -m hyper_smart_observer.dydx_v4.cli rest-health     # vérifier l'accès Indexer
python -m hyper_smart_observer.dydx_v4.cli leaderboard     # Job A: construire le classement (daily)
python -m hyper_smart_observer.dydx_v4.cli safety-check    # audit sécurité
# puis lancer l'observer (LANCER_HYPERSMART.cmd ou dashboard) et LAISSER TOURNER
```
Re-lancer `leaderboard` 1×/jour (la promotion ELITE exige 2 runs consécutifs).
Le PnL paper ne compte que les trades `data_source=REAL_INDEXER`
(`demo_data=true` est affiché si un trade démo s'est glissé dans la session).

## Garde-fous inchangés
READ-ONLY / PAPER-ONLY / DENY-BY-DEFAULT. 0 ordre réel, 0 clé privée, 0 signature,
0 dépôt/retrait. Un PnL paper positif ne garantit jamais un PnL réel positif.
