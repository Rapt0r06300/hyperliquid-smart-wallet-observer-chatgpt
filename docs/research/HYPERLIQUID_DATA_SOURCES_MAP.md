# Hyperliquid Data Sources Map

Date: 2026-06-02

HyperSmart uses Hyperliquid data in read-only mode. The map below separates
wide discovery sources from shortlist monitoring sources.

Historical PnL and wallet activity can guide research prioritization, but they
must never be presented as guaranteed profit or a live trading recommendation.

| Source Hyperliquid | Donnees disponibles | Vitesse | Limite | Usage dans HyperSmart | Risque |
|---|---|---|---|---|---|
| REST `/info` `allMids` | Mid prices for assets | Fast per call | REST weight | Mark prices for simulation and edge | Stale between calls |
| REST `/info` `clearinghouseState` | Current positions, margin summary | Medium | Per wallet REST budget | Warm snapshot and position diff | Not full trade history |
| REST `/info` `userFills` | Recent fills, closedPnl fields | Medium | Limited recent fills | Fill-level delta proof | Missing older fills |
| REST `/info` `userFillsByTime` | Time-ranged fills | Medium/slow | Page cap and timestamp pagination | Backfill / warm scan | Infinite loop if cursor bad |
| REST `/info` `openOrders` | Open orders | Medium | Per wallet REST budget | Context only | Not executed trades |
| REST `/info` `frontendOpenOrders` | Frontend open orders | Medium | Per wallet REST budget | Context only | Not executed trades |
| REST `/info` `historicalOrders` | Recent order history | Medium/slow | Heavy endpoint | Research only | Can be large |
| REST `/info` `portfolio` | Portfolio style stats | Medium | Per wallet budget | Historical scoring | Must not infer future |
| REST `/info` `userFees` | Fee info | Medium | Per wallet budget | Pessimistic fee calibration | Missing for unknown wallet |
| REST `/info` `userRateLimit` | User rate state | Medium | Per wallet budget | Diagnostics | Not signal |
| WS `trades` | Public trades by coin | Fast | Subscriptions / connections | Wide discovery, active wallet promotion | Does not expose full wallet quality |
| WS `allMids` | Live mids | Fast | Subscriptions | Mark open simulation positions | Stream gaps |
| WS `bbo` / `l2Book` | Liquidity and spread context | Fast | Subscription budget | Spread/slippage/liquidity scoring | Heavy if too many coins |
| WS `userFills` | User-specific fills | Fast | Max unique users | Hot shortlist deltas | Cannot follow thousands |
| WS `userEvents` | User-specific events | Fast | Max unique users | Future shortlist context | Must remain read-only |
| WS `orderUpdates` | User order updates | Fast | Max unique users | Context, never order creation | Ambiguous without fills |
| Explorer public UI | Public tx/activity display | Human-readable | Expensive/unstable | Manual/import/research only | Aggressive scraping forbidden |

## Scan Architecture

1. Cold scan: public imports, public trades, local DB, leaderboard snapshots.
2. Warm scan: bounded `/info` for at most a few leaders per run.
3. Hot scan: WebSocket read-only for selected leaders only.
4. Reports: missed opportunities, no-trades, PnL simulation, source health.

The architecture intentionally avoids "scan everything user-specific" because
that would break WebSocket limits and create unreliable results.
