"""
DydxEngine — moteur dYdX v4 thread-safe.

Démarre DydxLiveObserver dans un thread daemon.
Expose l'état via des accesseurs thread-safe.
PAPER-ONLY. Aucun ordre réel. Aucune clé privée.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from hyper_smart_observer.dydx_v4.cluster_detector import DydxClusterDetector
from hyper_smart_observer.dydx_v4.config import DydxV4Config, DydxNetwork, load_config_from_env
from hyper_smart_observer.dydx_v4.cosmos_client import DydxCosmosLcdClient
from hyper_smart_observer.dydx_v4.live_observer import DydxLiveObserver
from hyper_smart_observer.dydx_v4.rest_client import DydxIndexerRestClient, RestError
from hyper_smart_observer.dydx_v4.wallet_discovery import DydxWalletDiscovery
from hyper_smart_observer.dydx_v4.safety import assert_paper_only

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "dYdX v4 PAPER SIMULATION — READ-ONLY public Indexer API. "
    "No real orders. No real money. No private keys. No deposits. No withdrawals."
)


@dataclass
class EngineStatus:
    running: bool = False
    started_at_ms: int = 0
    network: str = "mainnet"
    rest_url: str = ""
    rest_healthy: bool = False
    iteration: int = 0
    wallets_in_shortlist: int = 0
    open_positions: int = 0
    net_pnl_usdt: float = 0.0
    equity_usdt: float = 1000.0
    total_trades: int = 0
    winrate: float = 0.0
    signals_refused: int = 0
    stale_refused: int = 0
    fees_paid: float = 0.0
    last_error: str = ""
    disclaimer: str = DISCLAIMER
    session_id: str = ""
    no_trade_reasons: dict = field(default_factory=dict)
    leader_exits: int = 0


class DydxEngine:
    """
    Moteur dYdX v4 — thread daemon paper-only.

    Usage:
        engine = DydxEngine()
        engine.start()
        status = engine.get_status()
        engine.stop()
    """

    def __init__(self, config: Optional[DydxV4Config] = None) -> None:
        self._config = config or load_config_from_env()
        # Par défaut: mainnet READ-ONLY pour scanner les vrais wallets
        if self._config.network.value == "testnet" and not config:
            import dataclasses
            self._config = dataclasses.replace(
                self._config, network=DydxNetwork.MAINNET, require_testnet=False
            )
        assert_paper_only(self._config)

        self._rest = DydxIndexerRestClient(
            base_url=self._config.indexer_rest_url,
            timeout_s=self._config.rest_timeout_s,
            max_retries=self._config.rest_max_retries,
            backoff_base_s=self._config.rest_backoff_base_s,
            rate_limit_rps=self._config.rest_rate_limit_rps,
        )

        self._cosmos = DydxCosmosLcdClient()
        self._cluster = DydxClusterDetector(
            consensus_window_ms=60_000,
            min_notional_usdc=5_000.0,
        )
        self._discovery = DydxWalletDiscovery(
            rest_client=self._rest,
            cosmos_client=self._cosmos,
        )
        self._observer: Optional[DydxLiveObserver] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._status = EngineStatus(
            network=str(self._config.network.value)
            if hasattr(self._config.network, "value")
            else str(self._config.network),
            rest_url=self._config.indexer_rest_url,
        )

    # ── public API ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le thread daemon paper-only."""
        assert_paper_only(self._config)
        if self._thread and self._thread.is_alive():
            logger.info("DydxEngine already running")
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            name="dydx-engine",
            daemon=True,
        )
        self._thread.start()
        logger.info("DydxEngine started | %s", DISCLAIMER)

    def stop(self) -> None:
        """Arrête l'observateur proprement."""
        if self._observer:
            self._observer.stop()
        logger.info("DydxEngine stopped")

    def get_status(self) -> dict:
        with self._lock:
            s = self._status
            return {
                "running": s.running,
                "started_at_ms": s.started_at_ms,
                "network": s.network,
                "rest_url": s.rest_url,
                "rest_healthy": s.rest_healthy,
                "iteration": s.iteration,
                "wallets_in_shortlist": s.wallets_in_shortlist,
                "open_positions": s.open_positions,
                "net_pnl_usdt": round(s.net_pnl_usdt, 4),
                "equity_usdt": round(s.equity_usdt, 4),
                "total_trades": s.total_trades,
                "winrate": f"{s.winrate:.0%}",
                "signals_refused": s.signals_refused,
                "stale_refused": s.stale_refused,
                "fees_paid": round(s.fees_paid, 4),
                "last_error": s.last_error,
                "disclaimer": s.disclaimer,
                "session_id": s.session_id,
                "no_trade_reasons": dict(
                    sorted(s.no_trade_reasons.items(), key=lambda x: -x[1])[:10]
                ),
                "leader_exits": s.leader_exits,
            }

    def get_wallets(self) -> list[dict]:
        if not self._observer:
            return []
        return [
            {
                "address": w.address,
                "subaccount": w.subaccount_number,
                "usdc_balance": round(w.usdc_balance, 2),
                "score": round(w.total_score, 4),
                "markets": [p.get("market", "") for p in (w.open_positions or [])],
            }
            for w in (self._observer._shortlist or [])
        ]

    def get_open_positions(self) -> list[dict]:
        if not self._observer:
            return []
        with self._lock:
            return [
                {
                    "position_id": pos.position_id,
                    "market_id": pos.market_id,
                    "side": pos.side,
                    "size": round(pos.size, 4),
                    "entry_price": round(pos.entry_price, 4),
                    "stop_loss": round(pos.stop_loss_price, 4),
                    "take_profit": round(pos.take_profit_price, 4),
                    "opened_at_ms": pos.opened_at_ms,
                    "wallet_count": pos.wallet_count,
                    "fee_paid": round(pos.fee_paid, 4),
                    "cluster_id": pos.cluster_id,
                }
                for pos in self._observer._open_positions.values()
            ]

    def get_closed_trades(self, limit: int = 50) -> list[dict]:
        if not self._observer:
            return []
        return list(self._observer._closed_trades[-limit:])

    def get_mark_prices(self) -> dict:
        if not self._observer:
            return {}
        return dict(self._observer._mark_prices)

    # ── internal ────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Boucle principale dans le thread daemon."""
        assert_paper_only(self._config)

        # Health check initial
        try:
            health = self._rest.get_health()
            with self._lock:
                self._status.rest_healthy = True
            logger.info("dYdX Indexer health OK: %s", health)
        except Exception as e:
            with self._lock:
                self._status.last_error = f"REST health check failed: {e}"
                self._status.rest_healthy = False
            logger.warning("dYdX Indexer health FAILED: %s", e)

        # Créer l'observer
        self._observer = DydxLiveObserver(
            config=self._config,
            rest_client=self._rest,
            cluster_detector=self._cluster,
            discovery=self._discovery,
            poll_interval_s=5.0,
            max_signal_age_ms=8_000,
        )

        with self._lock:
            self._status.running = True
            self._status.started_at_ms = int(time.time() * 1000)
            self._status.session_id = self._observer.stats.session_id

        # Patch: hook _poll_shortlist (nom exact) pour sync stats après chaque itération
        original_poll = self._observer._poll_shortlist

        def _patched_poll(*args, **kwargs):
            result = original_poll(*args, **kwargs)
            self._sync_stats()
            return result

        self._observer._poll_shortlist = _patched_poll

        # Timer de sync de secours: toutes les 3s (couvre discovery_running + positions)
        def _sync_timer():
            while self._observer and self._status.running:
                self._sync_stats()
                time.sleep(3.0)

        sync_thread = threading.Thread(target=_sync_timer, name="dydx-sync", daemon=True)
        sync_thread.start()

        try:
            self._observer.run()  # bloquant jusqu'à stop()
        except Exception as e:
            logger.error("DydxEngine loop error: %s", e, exc_info=True)
            with self._lock:
                self._status.last_error = str(e)
        finally:
            with self._lock:
                self._status.running = False
            logger.info("DydxEngine thread exited")

    def _sync_stats(self) -> None:
        """Synchronise les stats de l'observer vers EngineStatus."""
        if not self._observer:
            return
        s = self._observer.stats
        with self._lock:
            self._status.iteration += 1
            self._status.wallets_in_shortlist = len(self._observer._shortlist)
            self._status.open_positions = len(self._observer._open_positions)
            self._status.net_pnl_usdt = s.total_net_pnl_usdc
            self._status.equity_usdt = s.equity
            self._status.total_trades = s.positions_closed
            self._status.winrate = s.winrate
            self._status.signals_refused = s.signals_refused
            self._status.stale_refused = s.stale_signals_refused
            self._status.fees_paid = s.total_fees_paid
            # Injecter discovery_running dans last_error (UI feedback)
            if self._observer._discovery_running:
                self._status.last_error = "DISCOVERY_RUNNING"
            elif self._status.last_error == "DISCOVERY_RUNNING":
                self._status.last_error = ""
            # no_trade_reasons + leader_exits (viral bot)
            self._status.no_trade_reasons = dict(self._observer._no_trade_reasons)
            self._status.leader_exits = sum(
                1 for t in self._observer._closed_trades
                if t.get("reason") == "LEADER_EXIT"
            )


# Singleton global — thread-safe via .start()
_engine: Optional[DydxEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> DydxEngine:
    """Retourne le singleton DydxEngine (créé si inexistant)."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DydxEngine()
        return _engine


def start_engine() -> DydxEngine:
    """Démarre le moteur dYdX v4 (idempotent)."""
    engine = get_engine()
    engine.start()
    return engine
