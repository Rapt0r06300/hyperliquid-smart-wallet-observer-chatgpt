# Runbook Testnet dYdX v4

**Prérequis:** Python 3.10+, pip install requests websocket-client

## 1. Vérification de santé

```bash
python -m hyper_smart_observer.dydx_v4.cli runtime-check
python -m hyper_smart_observer.dydx_v4.cli safety-check
python -m hyper_smart_observer.dydx_v4.cli rest-health
```

## 2. Lister les marchés disponibles

```bash
python -m hyper_smart_observer.dydx_v4.cli markets
```

Vérifie que BTC-USD, ETH-USD, SOL-USD sont actifs.

## 3. Backfill d'un compte observé

```bash
# Remplacer par une vraie adresse dYdX v4 testnet
python -m hyper_smart_observer.dydx_v4.cli backfill \
    --address 0xADRESSE_TESTNET \
    --subaccount 0 \
    --max-pages 20
```

## 4. Dashboard paper

```bash
python -m hyper_smart_observer.dydx_v4.cli dashboard
```

Affiche (READ-ONLY):
- Balance paper courante
- Positions ouvertes
- PnL cumulé
- Derniers refus (no-trade)

## 5. Lancer un paper trade manuel (test)

```bash
python -m hyper_smart_observer.dydx_v4.cli paper \
    --market BTC-USD \
    --side LONG \
    --size 0.001
```

## 6. Tests unitaires

```bash
python -m pytest tests/dydx_v4/ -v
# Attendu: 77 passed, 0 failed
```

## 7. Variables d'environnement (testnet)

```bash
export DYDX_ENABLED=true
export DYDX_NETWORK=testnet         # TOUJOURS testnet d'abord
export DYDX_READ_ONLY=true          # non surchargeable
export DYDX_PAPER_ONLY=true         # non surchargeable
export DYDX_ALLOW_TRADING=false     # non surchargeable
export DYDX_MAX_SIGNAL_AGE_MS=4000
export DYDX_MIN_EDGE_BPS=30
export DYDX_STARTING_BALANCE_USDC=1000
export DYDX_MAX_OPEN_PAPER_TRADES=3
```

## Endpoints de santé

- `GET https://indexer.v4testnet.dydx.exchange/v4/height` → hauteur actuelle
- `GET https://indexer.v4testnet.dydx.exchange/v4/perpetualMarkets` → marchés
- `GET https://indexer.v4testnet.dydx.exchange/v4/fills?address=...` → fills

## En cas de problème

| Symptôme | Action |
|----------|--------|
| REST timeout | Vérifier connectivité réseau vers indexer.v4testnet.dydx.exchange |
| WS déconnexion | Normal — reconnect automatique après 5s |
| `require_testnet=True but network=mainnet` | Ne pas changer — c'est une sécurité |
| `allow_trading=True` ValueError | Ne jamais mettre allow_trading=True |
