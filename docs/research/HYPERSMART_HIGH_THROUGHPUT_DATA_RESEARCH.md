# HyperSmart High Throughput Data Research

Date: 2026-06-02

High throughput means local throughput, not API abuse.

## Viable approach

- Ingest public/read-only data into SQLite and optional columnar stores later.
- Maintain a local wallet index.
- Recompute priorities from local rows.
- Spend network budget only on shortlisted leaders.
- Use WebSocket public trades for broad discovery.
- Use user-specific streams only for up to 10 watched users.

## Current implementation

- `src/hl_observer/local_index` provides an in-memory local fallback index.
- `benchmark-local-scan --wallets 2000` measures local scan throughput without
  network.
- `scanner-priority-report` selects the next warm-scan wallets and logs skipped
  wallets.

## Future production options

- DuckDB or Parquet for larger local archives.
- Incremental refresh by timestamp.
- Materialized consensus tables.
- Separate writer queue to reduce SQLite lock contention.

