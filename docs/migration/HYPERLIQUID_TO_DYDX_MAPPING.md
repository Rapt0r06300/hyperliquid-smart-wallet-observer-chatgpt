# Mapping Hyperliquid → dYdX v4

## Endpoints

| Hyperliquid | dYdX v4 Indexer |
|-------------|-----------------|
| `https://api.hyperliquid.xyz/info` | `https://indexer.v4testnet.dydx.exchange` |
| WebSocket `wss://api.hyperliquid.xyz/ws` | `wss://indexer.v4testnet.dydx.exchange/v4/ws` |

## Identité

| Hyperliquid | dYdX v4 |
|-------------|---------|
| `wallet` (str) | `address` + `subaccountNumber` (int) |
| Pas de sous-compte | Subaccounts 0, 1, 2... |
| `leaderboard` endpoint | Pas d'équivalent direct — scraping positions |

## Fills

| Champ Hyperliquid | Champ dYdX v4 |
|-------------------|---------------|
| `coin` | `market` (ex: "BTC-USD") |
| `side` ("B"/"S") | `side` ("BUY"/"SELL") |
| `sz` | `size` |
| `px` | `price` |
| `fee` | `fee` |
| `time` (ms) | `createdAt` (ISO 8601) |
| `tid` | `id` |

## Positions

| Champ Hyperliquid | Champ dYdX v4 |
|-------------------|---------------|
| `szi` (signé) | `size` + `side` ("LONG"/"SHORT") |
| `entryPx` | `entryPrice` |
| `unrealizedPnl` | `unrealizedPnl` |
| `marginUsed` | `initialMargin` |

## Formules PnL (identiques)

```
LONG PnL  = (mark_price - entry_price) × size
SHORT PnL = (entry_price - mark_price) × size
```

## Scoring — critères communs

| Critère | Valeur |
|---------|--------|
| Winrate minimum | 40% |
| Profit factor minimum | 1.2 |
| Trades minimum | 10 |
| Contribution max d'un trade au PnL total | 70% |

## Ce qui N'existe PAS dans dYdX v4

- Pas de leaderboard public natif (contrairement à Hyperliquid)
- Pas d'endpoint `/info/leaderboard` — il faut identifier les smart wallets autrement
- Les fills nécessitent de connaître l'adresse du compte à l'avance
