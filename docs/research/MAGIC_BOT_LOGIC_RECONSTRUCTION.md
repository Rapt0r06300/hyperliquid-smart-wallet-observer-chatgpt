# Magic Bot Logic Reconstruction

Date: 2026-06-02

This reconstruction intentionally removes execution and profit claims. The
useful logic is a deterministic research pipeline:

1. Data first: ingest public/local history once.
2. Wallet aggregation: group fills/actions by wallet.
3. Anti-luck filters: reject one-big-win and concentrated PnL.
4. Target selection: rank wallets by consistency, activity and copyability.
5. Hot watch: follow only the bounded shortlist in real time.
6. Signal candidate: convert fresh open/add/reduce/close into a measurable
   candidate.
7. Edge after costs: subtract delay, spread, slippage, fees, liquidity and
   crowding.
8. Simulation without money: replay locally from a 1000 USDT virtual portfolio.
9. Feedback: promote/reduce wallets based on no-trade, missed opportunities and
   simulated results.

The HyperSmart hot path must remain:

`event -> normalize -> dedupe -> delta -> edge_remaining_bps -> risk gate -> local simulation or no-trade`

No LLM, no signature, no private key and no order belongs in that chain.

