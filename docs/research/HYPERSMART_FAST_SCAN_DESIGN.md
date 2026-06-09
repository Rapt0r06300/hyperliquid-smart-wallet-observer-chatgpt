# HyperSmart Fast Scan Design

Date: 2026-06-02

The fastest safe scanner is not the scanner that sends the most requests. It is
the scanner that spends scarce user-specific budget on the wallets most likely
to produce measurable, fresh, copyable events.

Fast scanning is not guaranteed profit. The scanner can only reduce missed data
and improve measurement quality; it cannot make future PnL certain.

## Layers

### Cold Scan

- Runs occasionally.
- Discovers wallets from imports, DB, public trades and manually supplied
  leaderboards.
- Rejects truncated or invalid addresses.
- Computes slow metrics such as history days, closedPnl points, drawdown and
  PnL concentration.

### Warm Scan

- Runs every 300 seconds by default.
- Uses REST `/info` read-only.
- Reads at most a small number of leaders per run by default.
- Stores snapshots and cursors.
- Produces position deltas and no-trade decisions.

### Hot Scan

- Uses WebSocket read-only.
- Follows shortlist users only.
- Max 10 user-specific users.
- Handles `isSnapshot` separately from updates.
- Routes fresh events into the same delta and SignalCandidate pipeline.

### Opportunity Scanner

- Scores wallets by activity, recency, historical quality, source health and
  missed opportunity cost.
- Logs skipped wallets/signals so we know whether the bot is too slow, too
  strict, underfunded, or blocked by rate limits.

## Priority Formula

`priority = activity + recency + quality + consensus + source_health - penalties`

Penalties include:

- stale data;
- low copyability;
- one-big-win risk;
- high drawdown;
- rate-limit pressure;
- repeated no-trade reasons;
- inactive wallet cooldown.

## Budgets

Default simulation-safe values:

- starting equity: 1000 USDT;
- max position notional: 50 USDT;
- max total exposure: 200 USDT;
- max open positions: 3;
- REST warm leaders per run: 3;
- WS user-specific users: 10;
- UI refresh: 1 second;
- scanner loop: bounded and stoppable.

## Missed Opportunity Reasons

- `STALE_SIGNAL`
- `RATE_LIMIT_GUARD`
- `WALLET_SKIPPED_BY_BUDGET`
- `NETWORK_READ_DISABLED`
- `SOURCE_UNAVAILABLE`
- `MISSING_CURRENT_MID`
- `EDGE_UNMEASURABLE`
- `EDGE_REMAINING_TOO_LOW`
- `LIQUIDITY_TOO_LOW`
- `COPY_DEGRADATION_TOO_HIGH`
- `NO_MATCHING_PAPER_POSITION_FOR_CLOSE`
- `MAX_OPEN_PAPER_TRADES_REACHED`

## Dashboard Expectations

The dashboard should show:

- wallets seen;
- wallets promoted;
- active shortlist;
- hot scan freshness;
- missed opportunities;
- accepted local simulations;
- no-trade reasons;
- equity and PnL from the 1000 USDT session.
