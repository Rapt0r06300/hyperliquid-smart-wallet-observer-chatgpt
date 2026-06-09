# Hyperliquid Smart Wallet Observer — Audit Complet PnL Négatif

**Date** : 2026-06-09  
**Périmètre** : Analyse des pertes systémiques en simulation paper  
**Statut** : AUDIT COMPLET + FIXMAP VALIDÉ  
**Projet** : HyperSmart Observer — Hyperliquid read-only, paper trading only

---

## 1. RÉSUMÉ EXÉCUTIF

### 1.1 État observé
- **P&L session** : -0.600599 USDC (réalisé -0.262828, latent -0.337771)
- **P&L journal complet** : -61.42333 USDC sur 1,372,800 événements
- **Gross P&L** : +14.215128 USDC
- **Frais** : -73.607792 USDC ⟹ **frais > edge brut**
- **Refus** : 1,321,463 / 1,372,800 (96.2 % rejection rate)

### 1.2 Verdict : Pas un bug, mais une **confluence de 5 causes racines**

```
┌─────────────────────────────────────────┐
│ ROOT CAUSES DE PnL NÉGATIF              │
├─────────────────────────────────────────┤
│ 1. Frais > Edge (73.61 > 14.21)         │
│ 2. Signaux âgés (45h median)            │
│ 3. Indexer non persistant (DB vide)     │
│ 4. Concurrence SQLite (database locked) │
│ 5. Wallets factices polluant LIVE PnL   │
└─────────────────────────────────────────┘
```

---

## 2. CAUSE 1 : FRAIS SUPÉRIEURS À L'EDGE BRUT

### 2.1 Diagnostic
- Edge attendu : ~14.21 USDC
- Frais appliqués : ~73.61 USDC
- **Ratio frais / edge** : 5.18x (mortel)

### 2.2 Problème
L'algorithme de calcul de `edge_remaining_bps` ne pénalise pas assez ou sous-estime les frais réels. Formule attendue :

```
edge_remaining_bps = expected_edge_bps - fees_rt_bps - spread_bps - slippage_bps - latency_bps - copy_degradation_bps
```

Mais les frais appliqués sont plus élevés que prévu.

### 2.3 Fixmap
- **Vérifier** : `edge_calculation.py` (ou équivalent) pour formule exacte
- **Bloquer** : signaux où `edge_remaining < 3 * total_fee_bps`
- **Logger** : détail des frais par trade simulé
- **Test** : `test_edge_remaining_calculation_includes_all_costs()`

---

## 3. CAUSE 2 : SIGNAUX ÂGÉS (45H MÉDIAN)

### 3.1 Diagnostic
- Tous les signaux rejetés ont `signal_age_ms > 4000` ms
- Médian observé : ~45 heures (ce n'est pas du live, c'est du **replay local**)

### 3.2 Problème
Le système refuse les signaux live parce qu'ils ne sont pas **frais**, mais les garde en **REPLAY LOCAL** pour backtest. Or, le PnL LIVE accumule les pertes du replay comme si c'était du LIVE.

### 3.3 Fixmap
- **Séparer** : mode `LIVE` vs `BACKTEST` vs `REPLAY` vs `TEST_FIXTURE`
- **Bloquer** : signal > `MAX_LIVE_SIGNAL_AGE_MS` (défaut 4000 ms) du PnL LIVE
- **Repla ACE** : uniquement en PnL BACKTEST séparé
- **Isoler** : wallets test (0x111..., 0x222...) dans TEST_FIXTURE
- **Dashboard** : afficher PnL LIVE, PnL BACKTEST, PnL REPLAY séparément
- **Test** : `test_signal_over_4s_excluded_from_live_pnl()`

---

## 4. CAUSE 3 : INDEXER NON PERSISTANT

### 4.1 Diagnostic
DB tables vides :
- `follow_signals` = 0
- `follow_decisions` = 0
- `paper_follow_orders` = 0
- `wallet_scores` = 0
- `positions` = 0
- `fills` = 0
- `position_deltas` = 0

Le pipeline de lecture des données ne persiste rien. Tout est en mémoire ou en replay local JSON.

### 4.2 Problème
L'absence de persistance forceLa reconstruction à chaque run. Pas de gap recovery. Pas de reconstruction continue de positions leader. Pas d'historique de signaux pour du backtest propre.

### 4.3 Fixmap
- **Créer** : `indexer_worker.py` qui persiste en continu
- **WebSocket** : `userFills` limité à 10 wallets (hot queue)
- **REST** : `userFillsByTime` + `userFills` pour gap recovery
- **Cursor** : par wallet pour reprendre from last known fill
- **Batch** : commits toutes les 30s ou tous les 100 fills
- **Snapshot** : `wallet_snapshots` chaque 5 min
- **Réconciliation** : compare local fills vs leader positions
- **Test** : `test_indexer_persists_fills_to_db()`

---

## 5. CAUSE 4 : CONCURRENCE SQLite

### 5.1 Diagnostic
Erreur observée : `database is locked`

### 5.2 Problème
SQLite en mode par défaut avec multiples readers/writers provoque des blocages.

### 5.3 Fixmap
- **Activer WAL** : `PRAGMA journal_mode = WAL`
- **Busy timeout** : `PRAGMA busy_timeout = 5000` (5s)
- **Connections pool** : créer une seule session writer, readers partageables
- **UI read-only** : jamais de writes depuis UI
- **Test** : `test_sqlite_concurrent_access_no_locked_error()`

---

## 6. CAUSE 5 : WALLETS FACTICES POLLUENT LIVE PnL

### 6.1 Diagnostic
Wallets test détectés :
- `0x1111111111111111111111111111111111111111`
- `0x2222222222222222222222222222222222222222`
- `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- `0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`
- `0x0000000000000000000000000000000000000000`

Inclus dans le journal PnL LIVE ⟹ **pertes fictives**.

### 6.2 Problème
Pas de filtre pour exclure les adresses de test du PnL LIVE.

### 6.3 Fixmap
- **Créer** : `TEST_FIXTURE_WALLET_ADDRESSES` constante
- **Filtrer** : exclure lors du calcul du PnL LIVE
- **Dashboard** : afficher PnL LIVE (no fixtures) + PnL ALL (avec fixtures)
- **Test** : `test_test_fixture_wallets_excluded_from_live_pnl()`

---

## 7. ARCHITECTURE OBLIGATOIRE : SÉPARATION DES MODES

```
┌─────────────────────────────────────────────────┐
│ MODES PROPOSÉS                                   │
├─────────────────────────────────────────────────┤
│ LIVE : frais réels, signaux < 4s, wallets vrais │
│ BACKTEST : frais sims, tous signaux             │
│ REPLAY : reconstruction jsonl, test only        │
│ TEST_FIXTURE : wallets 0x111..., neverPnL live  │
└─────────────────────────────────────────────────┘
```

### 7.1 Enum à créer
```python
class SimulationMode(str, Enum):
    LIVE = "live"           # Real signals, < 4s old, real wallets
    BACKTEST = "backtest"   # Replay historical, all signals
    REPLAY = "replay"       # Local jsonl, debug only
    TEST_FIXTURE = "test_fixture"  # 0x111..., never in LIVE
```

### 7.2 SignalSource à créer
```python
class SignalSource(str, Enum):
    FRESH = "fresh"         # Live WebSocket / REST < 4s
    REPLAY_JSONL = "replay_jsonl"  # Local replay
    BACKTEST_DB = "backtest_db"    # From DB
    TEST = "test"           # Fixtures
```

---

## 8. DÉTAILS TECHNIQUES PAR MISSION

### MISSION A : Séparation des modes
- [ ] Créer `SimulationMode` enum
- [ ] Créer `SignalSource` enum
- [ ] Filtrer: LIVE seulement si `mode=LIVE` ET `source=FRESH` ET `not test_wallet`
- [ ] Dashboard: 3 graphes (LIVE, BACKTEST, REPLAY)

### MISSION B : Fraîcheur des signaux
- [ ] Bloquer signal > 4000 ms du LIVE
- [ ] Repla CER signal > 4000 ms en BACKTEST
- [ ] Logger détail : `signal_age_ms`, `decision`, `reason`

### MISSION C : Indexer persistant
- [ ] `indexer_worker.py` : WebSocket userFills + REST gap
- [ ] Persist: `fills`, `positions`, `wallet_snapshots`
- [ ] Cursor per wallet
- [ ] Reconciliation loop

### MISSION D : SQLite
- [ ] WAL mode
- [ ] busy_timeout
- [ ] Connection pool
- [ ] Tests de concurrence

### MISSION E : Lifecyle
- [ ] Position state machine (OPEN, ADD, REDUCE, CLOSE, FLIP)
- [ ] No orphan closes
- [ ] Time-stop de sécurité

### MISSION F : Edge / Cost
- [ ] Bloquer edge_remaining < 3x total_cost
- [ ] Pénaliser coins illiquides
- [ ] Logs détail frais

### MISSION G : Scoring
- [ ] PnL net après frais
- [ ] Winrate, profit factor, expectancy
- [ ] Reject wallets suspects

### MISSION H : No-trade
- [ ] Chaque refus => table `rejected_signals`
- [ ] Dashboard affiche TOP refus
- [ ] Shadow evaluation possible

### MISSION I : Paper
- [ ] LONG: (mark - entry) * size
- [ ] SHORT: (entry - mark) * size
- [ ] No double-count frais
- [ ] Partial close correct

### MISSION J : Tests
- [ ] Suite complète sécurité
- [ ] DB concurrence
- [ ] Modes séparation
- [ ] Freshness

---

## 9. RÉSULTAT ATTENDU

Après fixes :

```
┌──────────────────────────────────────────────┐
│ AVANT (STATUS QUO)                            │
├──────────────────────────────────────────────┤
│ PnL LIVE (pollué) : -61.42 USDC              │
│ PnL BACKTEST : inconnu (pas séparé)          │
│ DB : vide                                     │
│ Frais/Edge : 5.18x                            │
│ Signaux âgés : 96% refusés                    │
└──────────────────────────────────────────────┘

                    ↓↓↓ FIXES ↓↓↓

┌──────────────────────────────────────────────┐
│ APRÈS (OBJECTIF)                              │
├──────────────────────────────────────────────┤
│ PnL LIVE (clean) : mieux analysé              │
│ PnL BACKTEST : séparé, transparent            │
│ DB : persistant (fills, positions, scores)    │
│ Frais/Edge : < 3x (gate bloquant > 3x)        │
│ Signaux âgés : 0% du LIVE                     │
│ Dashboard : 3 courbes claires                 │
│ Tests : suite complète verte                  │
└──────────────────────────────────────────────┘
```

---

## 10. SÉCURITÉ ABSOLUE

- ✅ **0 ordre réel** : Pas d'appel `/exchange`
- ✅ **0 clé privée** : Aucune demande
- ✅ **0 signature** : Read-only
- ✅ **0 mainnet** : Simulation paper uniquement
- ✅ **Kill switch** : Fonctionnel
- ✅ **No-trade logic** : Explicite par mode

---

## 11. TIMELINE

Phase 1 (now) : Séparation modes + Freshness + Wallets test
Phase 2 : Indexer persistant + SQLite WAL
Phase 3 : Edge/Cost recalc + Lifecycle
Phase 4 : Tests complets + Dashboard refresh

---

## CONCLUSION

Le P&L négatif **n'est pas un bug caché**, c'est le résultat attendu d'un système **trop permissif et mélangé** :
- signaux trop vieux traités comme frais
- frais sous-estimés
- wallets test polluting metrics
- pas de persistence

Les **fixes proposées** restaurent la **séparation logique** et la **transparence** sans jamais risquer la sécurité.

