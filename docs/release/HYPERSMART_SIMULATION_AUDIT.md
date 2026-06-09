# HyperSmart Simulation Audit

Date: 2026-06-02

## Where The Active Simulation Lives

- User-facing launcher: `LANCER_HYPERSMART.cmd`
- Startup script: `tools/start_hypersmart_simulation.ps1`
- Poll loop: `tools/hypersmart_simulation_poll_loop.ps1`
- UI routes: `src/hl_observer/ui/routes.py`
- Persistent UI state: `src/hl_observer/ui/persistent_state.py`
- Score engine: `src/hl_observer/copying/realtime_magic_score.py`
- State file: `data/runtime/ui_simulation_state.json`

## Capital And Caps

- Starting equity: 1000 USDT fictive.
- Max position notional: 50 USDT.
- Max total exposure: 200 USDT.
- No real wallet balance is read.
- No testnet balance is read.
- No mainnet balance is read.

## What Is Implemented

- Fresh-only simulation from UI session start.
- Persistent state until reset/launcher restart.
- Virtual positions.
- Entry costs.
- Realized/unrealized PnL.
- Equity history.
- Consensus cluster local positions.
- Refusals/no-trade events.
- Dashboard rendering.

## What Is Partially Implemented

- Leader close/reduce following exists for matching local positions, but needs
  more historical replay tests across many coins.
- Drawdown is visible through equity history but needs a dedicated drawdown
  field in every report.
- Liquidity uses conservative scoring; BBO/L2 integration can be improved.

## What Is Not Implemented

- Real orders.
- Testnet executor.
- Mainnet.
- `/exchange`.
- Private key handling.
- Guaranteed profit logic.

## Verdict

The current simulation is not a facade: it stores state, accepts/refuses events,
updates PnL and tracks positions. It remains incomplete as a professional-grade
research simulator because larger local historical replay, richer drawdown
metrics and persistent local index integration still need expansion.

## 2026-06-07 Anti-Lookahead Update

- `strategy-tournament` now selects candidate configs using train + validation only.
- Holdout is verification-only and is reported with `holdout_failed_after_selection`.
- `NO_TRADE`, duplicate/ignored events and state cleanup rows cannot be counted as selected profitable trades.
- On the current local decision journal, the honest best config is `no_trade_baseline`.
- This means the current logs do not prove a profitable copy strategy; forcing trades would be overfit or fake-profit behavior.
- The safe next action is fresh read-only collection plus stricter acceptance, not hiding losses.

## 2026-06-07 Runtime Write Diagnostics

- Added `runtime-write-check` to verify whether `logs/logs à envoyer` and the replay outputs can be refreshed.
- Added `GATE_RUNTIME_WRITES` to `quality-gates`.
- Added launcher warnings when the runtime log folder is not writable.
- Added replay write warnings to `realtime-health`.
- Current local evidence can show two separate blockers: stale trading data and locked/non-writable runtime outputs. These must not be confused with a profitable or unprofitable strategy decision.
- The simulator remains read-only: no order, no `/exchange`, no signature, no key, no mainnet.
