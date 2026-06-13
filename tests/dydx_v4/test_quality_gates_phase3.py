from __future__ import annotations

import time
from unittest.mock import MagicMock

from hyper_smart_observer.dydx_v4.cluster_detector import ClusterSignal, DydxClusterDetector
from hyper_smart_observer.dydx_v4.config import DydxNetwork, DydxV4Config
from hyper_smart_observer.dydx_v4.live_observer import DydxLiveObserver
from hyper_smart_observer.dydx_v4.market_flow import FlowSignal, build_cluster_from_flow


def _book(mid: float = 100.0, spread_bps: float = 2.0, size: float = 100.0) -> dict:
    half = mid * spread_bps / 2 / 10_000
    return {
        "bids": [{"price": str(mid - half), "size": str(size)} for _ in range(5)],
        "asks": [{"price": str(mid + half), "size": str(size)} for _ in range(5)],
    }


def _observer(*, max_spread_bps: float = 8.0, flow_min_trades: int = 12) -> DydxLiveObserver:
    cfg = DydxV4Config(
        network=DydxNetwork.TESTNET,
        market_flow_enabled=False,
        consensus_min_wallets=1,
        max_spread_bps=max_spread_bps,
        flow_min_trades=flow_min_trades,
    )
    rest = MagicMock()
    rest.get_orderbook.return_value = _book()
    rest.get_candles.return_value = {"candles": []}
    rest.get_market.return_value = {"markets": {"ETH-USD": {"nextFundingRate": "0"}}}
    obs = DydxLiveObserver(
        config=cfg,
        rest_client=rest,
        cluster_detector=DydxClusterDetector(consensus_window_ms=60_000, min_notional_usdc=0.0),
        initial_shortlist=[],
        poll_interval_s=0.01,
        max_signal_age_ms=8_000,
    )
    obs._mark_prices["ETH-USD"] = 100.0
    return obs


def _flow_cluster(*, trades: int = 30, total_usdc: float = 50_000.0) -> ClusterSignal:
    buy = total_usdc if total_usdc > 0 else 0.0
    signal = FlowSignal(
        market="ETH-USD",
        direction="LONG",
        buy_usdc=buy,
        sell_usdc=0.0,
        trades=trades,
    )
    return build_cluster_from_flow(signal, mark_price=100.0, now_ms=int(time.time() * 1000))


def test_spread_gate_refuses_wide() -> None:
    obs = _observer(max_spread_bps=8.0)
    obs.rest.get_orderbook.return_value = _book(spread_bps=120.0, size=100.0)

    obs._evaluate_cluster(_flow_cluster(trades=30, total_usdc=60_000.0))

    assert obs.stats.positions_opened == 0
    assert any(reason.startswith("SPREAD_TOO_WIDE") for reason in obs._no_trade_reasons)


def test_book_too_thin_refused() -> None:
    obs = _observer(max_spread_bps=8.0)
    obs.rest.get_orderbook.return_value = _book(spread_bps=2.0, size=0.001)

    obs._evaluate_cluster(_flow_cluster(trades=30, total_usdc=60_000.0))

    assert obs.stats.positions_opened == 0
    assert any(reason.startswith("BOOK_TOO_THIN") for reason in obs._no_trade_reasons)


def test_flow_min_trades_refused() -> None:
    obs = _observer(flow_min_trades=12)

    obs._evaluate_cluster(_flow_cluster(trades=2, total_usdc=60_000.0))

    assert obs.stats.positions_opened == 0
    assert any(reason.startswith("FLOW_MIN_TRADES") for reason in obs._no_trade_reasons)

