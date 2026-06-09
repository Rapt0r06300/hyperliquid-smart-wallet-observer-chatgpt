# Plan de correction PnL — dYdX v4

## Objectif

Maximiser la probabilité d'un PnL paper positif réaliste sur dYdX v4.
**Jamais de promesse de PnL toujours positif — impossible à garantir.**

## Levier 1 — Moins de trades, meilleure sélection

### Filtre qualité signal
```python
# Seuils actuels (config.py)
min_edge_bps = 30.0           # edge net minimum
edge_safety_multiplier = 3.0  # edge > 3x total_cost
max_signal_age_ms = 4000      # signal fraîcheur max
```

### Filtre qualité leader
```python
# scoring.py
min_winrate = 0.40            # 40% de trades gagnants
min_profit_factor = 1.2       # profits / pertes > 1.2
min_trades_required = 10      # historique suffisant
max_one_trade_contribution = 0.70  # pas de lucky shot
```

## Levier 2 — Prix d'entrée pessimiste

Le paper simulator applique systématiquement les coûts au pire prix:
```python
# paper.py open_position()
pessimistic_price = mark_price * (1 + (spread_bps + slippage_bps) / 10_000)
# Pour un LONG: on achète au-dessus du mid
# Pour un SHORT: on vend en-dessous du mid
```

## Levier 3 — Stopper rapidement les pertes

Règles de protection (à implémenter en Phase 2):
- Refus d'ouvrir si position déjà perdante sur ce marché
- Stop-loss automatique à -50% de l'edge attendu
- Cooldown de 30min après un close en perte

## Levier 4 — Coûts complets et non-doublés

La formule PnL nette utilise les frais aller-retour:
```python
# models.py PaperTrade.compute_pnl()
LONG:  gross = (mark - entry) × size
SHORT: gross = (entry - mark) × size
fees  = notional × (fee_bps / 10_000) × 2  # aller + retour, jamais × 4
net   = gross - fees
```

## Métriques cibles (paper)

| Métrique | Seuil minimum | Seuil cible |
|----------|--------------|-------------|
| Winrate | 40% | 55% |
| Profit factor | 1.2 | 1.5 |
| Sharpe annualisé | 0.5 | 1.0 |
| Max drawdown | < 30% | < 15% |

## Ce qui ne sera jamais promis

- PnL "toujours positif" — n'existe pas en trading
- Garantie de performance future basée sur le passé
- Résultats paper = résultats réels

## Prochaines étapes pour améliorer le PnL paper

1. Collecter 30 jours de données sur testnet
2. Identifier 5-10 smart wallets dYdX v4 avec bon historique
3. Backtester sur ces données avec les paramètres actuels
4. Ajuster les seuils selon les résultats (sans overfitting)
5. Passer en paper live sur 7 jours
6. Analyser et ajuster
