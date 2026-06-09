# Plan de migration Hyperliquid → dYdX v4

**Branche:** `migration-dydx-v4-and-pnl-audit`  
**Statut:** En cours — module dYdX v4 créé, 77/77 tests verts  
**Mode:** Simulation paper uniquement. Aucun ordre réel.

## Principe directeur

On ne supprime pas Hyperliquid. On ajoute dYdX v4 proprement dans
`hyper_smart_observer/dydx_v4/` avec une architecture complète et indépendante.
Hyperliquid reste en fallback/comparatif.

## Phases

### Phase 1 — Fondations (TERMINÉ)
- [x] Module `hyper_smart_observer/dydx_v4/` créé (18 fichiers)
- [x] Config safe by default (DYDX_ENABLED=false, PAPER_ONLY=true)
- [x] Modèles normalisés (NormalizedFill, NormalizedPosition, etc.)
- [x] Client REST Indexer (GET-only, retry, backoff, rate limit)
- [x] Client WebSocket Indexer (reconnect, gap detection)
- [x] Storage SQLite WAL (22 tables, déduplication)
- [x] Lifecycle engine (OPEN/ADD/REDUCE/CLOSE/orphan)
- [x] Paper simulator (sessions isolées par mode)
- [x] Signal engine + no-trade engine
- [x] Scoring + shortlist
- [x] Backtest/Replay (jamais en mode LIVE)
- [x] CLI + dashboard adapter (READ-ONLY)
- [x] 77/77 tests verts

### Phase 2 — Intégration données réelles (À FAIRE)
- [ ] Backfill fills depuis l'Indexer testnet
- [ ] Identifier les smart wallets actifs sur dYdX v4
- [ ] Scorer et shortlister les comptes
- [ ] Valider lifecycle engine sur données réelles

### Phase 3 — Paper trading live (À FAIRE)
- [ ] Activer DYDX_ENABLED=true sur testnet
- [ ] Connecter WebSocket pour signaux temps réel
- [ ] Collecter PnL paper sur 48h minimum
- [ ] Comparer résultats Hyperliquid vs dYdX

### Phase 4 — Documentation et audit final (À FAIRE)
- [ ] Audit de sécurité complet
- [ ] Rapport PnL paper vs PnL Hyperliquid
- [ ] Décision: migration complète ou mode dual

## Priorités techniques

1. **Sécurité absolue** — jamais un ordre réel, jamais une clé privée
2. **Qualité des signaux** — moins de trades mais plus propres
3. **Isolation des modes** — LIVE/BACKTEST/REPLAY/TEST_FIXTURE séparés
4. **Traçabilité** — tout refus est loggé avec raison typée (NoTradeReason)
