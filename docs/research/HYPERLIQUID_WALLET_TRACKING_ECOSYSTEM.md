# Hyperliquid Wallet Tracking Ecosystem

Date: 2026-06-02

Public ecosystem signals:

- Hyperliquid official `/info` and WebSocket docs provide the core read-only
  data needed by HyperSmart.
- HyperTracker and HyData show that large-scale wallet analytics require
  pre-indexed data and cannot be replicated by naive per-wallet polling.
- Open-source copy-trading repos demonstrate real-time monitoring and sizing
  patterns, but their execution/private-key paths are intentionally excluded.
- Community comments repeatedly warn that latency, thin books, partial fills
  and execution gap are where paper strategies fail.

HyperSmart translation:

- local index first;
- warm REST scan second;
- hot shortlist WS third;
- virtual simulation only;
- missed-opportunity report to explain blind spots.

