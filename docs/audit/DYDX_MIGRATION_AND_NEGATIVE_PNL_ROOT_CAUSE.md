# Audit — Causes du PnL négatif Hyperliquid + Plan dYdX v4

## Contexte

L'audit du système Hyperliquid a révélé 5 causes racines du PnL négatif.
Ce document analyse comment le module dYdX v4 les corrige architecturalement.

## Les 5 causes racines (Hyperliquid)

### 1. Signaux trop vieux
**Problème:** Des signaux datant de plusieurs secondes étaient encore traités.  
**Impact:** Prix d'entrée significativement dégradé.  
**Fix dYdX v4:**
- `max_signal_age_ms=4000` (rejet hard à 4s)
- `hard_max_signal_age_ms=8000` (rejet absolu à 8s)
- Vérification dans `DydxSignalEngine.evaluate_delta()`

### 2. Coûts sous-estimés
**Problème:** Seuls les frais taker étaient comptabilisés. Spread, slippage
et dégradation de copie étaient ignorés.  
**Impact:** Edge apparent positif, edge réel négatif.  
**Fix dYdX v4:**
```
edge_remaining = edge_brut
    - taker_fee_bps × 2   (entrée + sortie)
    - estimated_spread_bps
    - estimated_slippage_bps
    - estimated_latency_bps
    - copy_degradation_bps
```
Seuil: `edge_remaining > max(30bps, 3× total_cost_bps)`

### 3. Orphan closes comptabilisés comme PnL réel
**Problème:** Des closes sans position locale étaient traités et généraient
des PnL fictifs (souvent négatifs).  
**Impact:** PnL live pollué.  
**Fix dYdX v4:**
- Détection orphan précoce dans `DydxLifecycleEngine.process_fill()`
- Orphan close → `is_orphan=True`, refusé, jamais comptabilisé
- Loggé dans `_orphan_events` pour audit

### 4. Leaders perdants shortlistés
**Problème:** Des comptes avec winrate < 30% ou profit_factor < 1.0
étaient quand même copiés faute de données suffisantes.  
**Impact:** Copie de positions perdantes.  
**Fix dYdX v4:**
- `compute_account_score()` : winrate ≥40%, profit_factor ≥1.2
- Minimum 10 trades pour être shortlisté
- Un trade ne peut pas représenter plus de 70% du PnL total

### 5. Mélange LIVE/BACKTEST
**Problème:** Les PnL de backtests contaminaient les métriques live.  
**Impact:** Illusion de performance, décisions basées sur des données fausses.  
**Fix dYdX v4:**
- `PaperSession` isolée par `SimulationMode`
- `DydxBacktester.run_on_fills()` lève ValueError si mode=LIVE
- TEST_FIXTURE addresses exclues automatiquement du LIVE

## État des corrections en Phase 1

| Cause | Corrigée | Test |
|-------|----------|------|
| Signaux trop vieux | ✅ | `test_stale_signal_refused` |
| Coûts sous-estimés | ✅ | `test_edge_below_threshold` |
| Orphan closes | ✅ | `test_orphan_close_refused` |
| Leaders perdants | ✅ | `test_compute_account_score_*` |
| Mélange modes | ✅ | `test_backtest_pnl_stays_in_backtest` |

## Données Hyperliquid actuelles

```
fills: 0
positions: 0
signals: 0
paper_trades: 0
leaders shortlistés: 0
refuses: 600+
```

Le système Hyperliquid n'a jamais produit de données utilisables (SOURCE_UNAVAILABLE).
C'est la raison principale de la migration vers dYdX v4 dont les données
sont accessibles via l'Indexer public.
