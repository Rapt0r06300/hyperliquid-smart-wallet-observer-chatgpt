# dYdX v4 — Politique de risque (anti-perte)

> READ-ONLY · PAPER-ONLY · opt-in `DYDX_RISK_POLICY=1` · défaut OFF.
> Module : `hyper_smart_observer/dydx_v4/risk_policy.py` (logique pure, testée).

Les 4 leviers demandés pour pousser vers un PnL positif (sans jamais maquiller
un chiffre ni garantir le profit) :

## 1. Anti-churn (le « 1-2 s »)
- `held_long_enough(opened_at_ms, now, min_hold_s)` : on ne ferme pas sur sortie
  leader avant `min_hold_seconds` (défaut 20 s). Câblé dans `_handle_leader_close`
  (remplace l'ancien garde fixe de 5 s). **Ne bloque pas un vrai stop-loss.**
- `reopen_allowed(last_close, now, cooldown_s)` : pas de réouverture d'un marché
  avant `reopen_cooldown_seconds` (défaut 30 s). Câblé en Gate 0 de `_evaluate_cluster`.

## 2. Exits ATR (volatilité)
- `rolling_atr(prices)` + `atr_exit_decision(...)` : stop / take-profit / trailing
  dimensionnés sur l'ATR (laisser courir les gagnants, couper vite les perdants).
- **Déjà actifs** dans le moteur via `_check_exits` (SL/TP/trailing/time-stop posés
  à l'ouverture de chaque position). `risk_policy` fournit en plus la version pure
  testable, réutilisable.

## 3. Coupe-circuit drawdown
- `CircuitBreaker` : bloque les **nouvelles** entrées si
  `consecutive_losses ≥ circuit_max_consecutive_losses` (défaut 4) **ou**
  `perte du jour ≥ circuit_max_daily_drawdown_pct × capital` (défaut 5 %).
  Se réarme automatiquement chaque jour. Câblé en Gate 0 (entrée) + alimenté à
  chaque fermeture dans `_close_paper_position`.

## 4. Anti-scalper
- `is_scalper(median_hold_seconds, scalper_min_hold_seconds)` : écarte les leaders
  dont la détention médiane < seuil (défaut 60 s) — on ne bat pas un scalpeur sur
  la latence. Câblé en Gate 0. **Best-effort** : si la durée de détention du leader
  n'est pas connue (`None`), aucun filtrage (graceful) → à enrichir quand le
  harvester fournira la durée médiane par wallet.

## Réglages (env, défauts sûrs)

| Env | Défaut | Rôle |
|-----|--------|------|
| `DYDX_RISK_POLICY` | 0 (lanceur: 1) | activer la politique |
| `DYDX_MIN_HOLD_SECONDS` | 20 | hold mini avant sortie leader |
| `DYDX_REOPEN_COOLDOWN_SECONDS` | 30 | cooldown réouverture |
| `DYDX_CIRCUIT_MAX_CONSECUTIVE_LOSSES` | 4 | coupe-circuit pertes d'affilée |
| `DYDX_CIRCUIT_MAX_DAILY_DD_PCT` | 0.05 | coupe-circuit perte jour |
| `DYDX_SCALPER_MIN_HOLD_SECONDS` | 60 | seuil anti-scalper |
| `DYDX_ADAPTIVE_EXITS` | 1 | exits ATR |

## Sécurité & câblage

- Tout est **gardé** par `if self._risk_breaker is not None` → flag OFF =
  comportement inchangé. Init en try/except (un échec retombe sur le moteur normal).
- `risk_policy.py` n'a **aucune** méthode d'ordre/signature/dépôt — lecture & calcul.
- Tests purs : `tests/dydx_v4/test_risk_policy.py` (à exécuter via pytest côté machine).
