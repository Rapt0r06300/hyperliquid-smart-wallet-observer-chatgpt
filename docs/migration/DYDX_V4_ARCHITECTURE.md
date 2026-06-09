# Architecture dYdX v4

## Vue d'ensemble

```
hyper_smart_observer/dydx_v4/
├── __init__.py          # Module declaration + __safety__
├── config.py            # DydxV4Config, safe defaults
├── safety.py            # Gates de sécurité absolue
├── models.py            # Modèles normalisés
├── rest_client.py       # Client REST Indexer (GET-only)
├── ws_client.py         # Client WebSocket Indexer
├── normalizer.py        # Raw → NormalizedFill/Position/etc.
├── storage.py           # SQLite WAL, 22 tables, déduplication
├── lifecycle.py         # OPEN/ADD/REDUCE/CLOSE/orphan
├── scoring.py           # Score compte, shortlist
├── signals.py           # Signal engine + gates
├── no_trade.py          # No-trade engine + rapport
├── paper.py             # Paper simulator (sessions isolées)
├── backtest.py          # Backtest/Replay (jamais LIVE)
├── indexer.py           # Orchestration REST+WS+backfill
├── cli.py               # CLI paper/backfill/dashboard
└── dashboard_adapter.py # Dashboard READ-ONLY
```

## Flux de données

```
Indexer REST (snapshots) ──┐
                            ├─→ normalizer ─→ storage (SQLite)
Indexer WS (temps réel) ───┘         │
                                      ├─→ lifecycle engine
                                      │         │
                                      │         ├─→ scoring
                                      │         │         │
                                      │         └─→ signals ─→ no_trade (log)
                                      │                    │
                                      │                    └─→ paper simulator
                                      │                               │
                                      └─→ dashboard adapter ←─────────┘
```

## Concepts clés dYdX v4 vs Hyperliquid

| Concept | Hyperliquid | dYdX v4 |
|---------|-------------|---------|
| Identité | wallet address | account address + subaccount number |
| Marché | coin | market_id (ex: BTC-USD) |
| API | Hyperliquid API | Indexer REST + WebSocket |
| Réseau | mainnet/testnet | v4testnet / mainnet |
| Frais | 0.035% taker | 0.05% taker |
| Pagination | cursor offset | createdBeforeOrAt ISO |

## Clé de position

Format: `dydx_v4|{network}|{account}|{subaccount}|{market}|{side}`

Exemple: `dydx_v4|testnet|0xabc...def|0|BTC-USD|LONG`

## Isolation des modes

| Mode | PnL | Rôle |
|------|-----|------|
| LIVE | session LIVE isolée | Observer temps réel testnet |
| BACKTEST | session BACKTEST isolée | Rejeu historique |
| REPLAY | session REPLAY isolée | Debug, recherche |
| TEST_FIXTURE | toujours exclu du LIVE | Adresses de test |

## Endpoints (READ-ONLY, pas d'authentification)

- REST testnet: `https://indexer.v4testnet.dydx.exchange`
- WS testnet: `wss://indexer.v4testnet.dydx.exchange/v4/ws`
- REST mainnet: `https://indexer.dydx.trade`
- WS mainnet: `wss://indexer.dydx.trade/v4/ws`
