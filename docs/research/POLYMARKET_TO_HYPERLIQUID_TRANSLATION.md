# Polymarket To Hyperliquid Translation

Date: 2026-06-02

| Logique Polymarket | Equivalent Hyperliquid | Donnee necessaire | Source | Module actif |
|---|---|---|---|---|
| wallet buys YES/NO | wallet opens long/short | `dir`, `startPosition`, signed position | `/info`, WS | delta/lifecycle |
| wallet exits market | wallet close/reduce | `closedPnl`, position change | `/info`, WS | lifecycle |
| market price | coin mid/BBO/L2 | `allMids`, `bbo`, `l2Book` | `/info`, WS | edge/simulation |
| top wallet | wallet quality/copyability | closedPnl, drawdown, consistency | local index | scoring/intelligence |
| copy delay | signal age | exchange time, receive time | local/WS | edge |
| market crowd | coin/direction consensus | deltas in short window | local index | consensus |
| order book slippage | slippage/spread penalty | mids/BBO/L2 | `/info`, WS | simulation costs |
| no-trade filter | refused signal | missing edge/liquidity/freshness | local | no-trade/missed |

Translation rule: a Polymarket copy bot executes; HyperSmart observes and
simulates only. The closest safe equivalent is a local virtual portfolio.

