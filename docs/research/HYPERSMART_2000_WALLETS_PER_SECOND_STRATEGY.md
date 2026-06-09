# HyperSmart 2000 Wallets Per Second Strategy

Date: 2026-06-02

Target:

`HYPERSMART_LOCAL_SCAN_TARGET_WALLETS_PER_SECOND=2000`

Meaning:

- scan 2000 locally indexed wallets per second;
- no network calls per wallet;
- no 2000 WebSocket streams;
- no bypass of Hyperliquid limits.

Implemented command:

```powershell
python -m hl_observer benchmark-local-scan --wallets 2000
```

The command generates fake local wallets, indexes them, scans them, and reports
throughput. It is a performance contract for local analysis only.

