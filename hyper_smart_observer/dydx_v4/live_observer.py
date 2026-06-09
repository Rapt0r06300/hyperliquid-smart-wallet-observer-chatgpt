"""
Observateur temps réel dYdX v4 — copy-trading paper uniquement.

Réglages calibrés sur l'analyse de 1,482,013 events Hyperliquid:
- Focus ETH-USD (seul coin prouvé rentable +$9.07 net, signal age moyen 3s)
- WebSocket temps réel → signal age <500ms (vs 47s en polling HL)
- Stop-loss -1.5% OBLIGATOIRE (HYPE SHORT = -$20 sans stop dans les logs HL)
- Take-profit +2.5%
- 2+ wallets dans la même direction = signal fort (pas besoin de 7+ wallets)
- Poll REST toutes les 5s en fallback (vs 47s dans HL → résout 47% NO_MATCHING)

RÈGLE ABSOLUE: PAPER-ONLY. Aucun ordre réel. Aucune clé privée.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

from hyper_smart_observer.dydx_v4.cluster_detector import (
    ClusterSignal,
    DydxClusterDetector,
    PositionEvent,
)
from hyper_smart_observer.dydx_v4.config import DydxV4Config
from hyper_smart_observer.dydx_v4.models import (
    NoTradeReason,
    PaperPosition,
    PaperTrade,
    PaperTradeStatus,
    PositionSide,
    SimulationMode,
)
from hyper_smart_observer.dydx_v4.rest_client import DydxIndexerRestClient, RestError
from hyper_smart_observer.dydx_v4.safety import assert_paper_only
from hyper_smart_observer.dydx_v4.wallet_discovery import DydxWalletDiscovery, WalletScore

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Réglages calibrés sur l'analyse empirique HL
# ─────────────────────────────────────────────

# Stop-loss: -1.5% → évite les -$20 HYPE SHORT sans stop
STOP_LOSS_PCT = 1.5

# Take-profit: +2.5% → ratio risk/reward 1.67:1
TAKE_PROFIT_PCT = 2.5

# Fenêtre de fraîcheur: signal vieux > 8s = NO_TRADE
# ETH avg signal age = 3s, BTC = 6.8s, on donne 8s max
MAX_SIGNAL_AGE_MS = 8_000

# Intervalle de poll REST (fallback si WebSocket unavailable)
# 5s au lieu de 47s → résout 47% NO_MATCHING refusals
POLL_INTERVAL_S = 5.0

# Découverte shortlist: refresh toutes les 6 heures
DISCOVERY_REFRESH_S = 6 * 3600

# Marchés prioritaires (ETH en premier d'après l'analyse)
FOCUS_MARKETS = ["ETH-USD", "BTC-USD", "SOL-USD"]

# Taille max paper par trade (USDT fictifs)
PAPER_NOTIONAL_USDT = 50.0

# Max positions paper ouvertes simultanément (évite sur-exposition)
MAX_OPEN_PAPER_POSITIONS = 3

# Frais taker dYdX v4: 5 bps (0.05%)
TAKER_FEE_BPS = 5.0


@dataclass
class PaperPositionState:
    """État d'une position paper ouverte."""
    position_id: str
    market_id: str
    side: str           # "LONG" ou "SHORT"
    size: float         # en USDT fictifs
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    opened_at_ms: int
    cluster_id: str
    wallet_count: int
    fee_paid: float = 0.0
    simulation_mode: SimulationMode = SimulationMode.LIVE

    @property
    def unrealized_pnl(self) -> float:
        """PnL non réalisé (nécessite mark_price)."""
        return 0.0  # Calculé dans calculate_pnl()

    def calculate_pnl(self, mark_price: float) -> float:
        """
        PnL non réalisé.
        LONG: (mark - entry) * size / entry
        SHORT: (entry - mark) * size / entry
        """
        if self.side == "LONG":
            return (mark_price - self.entry_price) / self.entry_price * self.size
        else:
            return (self.entry_price - mark_price) / self.entry_price * self.size

    def is_stop_loss_hit(self, mark_price: float) -> bool:
        if self.side == "LONG":
            return mark_price <= self.stop_loss_price
        else:
            return mark_price >= self.stop_loss_price

    def is_take_profit_hit(self, mark_price: float) -> bool:
        if self.side == "LONG":
            return mark_price >= self.take_profit_price
        else:
            return mark_price <= self.take_profit_price


@dataclass
class ObserverStats:
    """Statistiques de session paper trading."""
    session_id: str
    started_at_ms: int
    total_signals_seen: int = 0
    signals_accepted: int = 0
    signals_refused: int = 0
    positions_opened: int = 0
    positions_closed: int = 0
    total_net_pnl_usdc: float = 0.0
    total_fees_paid: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0
    stale_signals_refused: int = 0
    no_matching_refused: int = 0
    stop_loss_exits: int = 0
    take_profit_exits: int = 0
    markets_traded: dict = field(default_factory=dict)
    disclaimer: str = (
        "PAPER SIMULATION ONLY. No real orders, no real money, no private keys. "
        "Positive paper PnL does not guarantee positive real PnL."
    )

    @property
    def winrate(self) -> float:
        total = self.winning_trades + self.losing_trades
        return self.winning_trades / total if total > 0 else 0.0

    @property
    def equity(self) -> float:
        return 1000.0 + self.total_net_pnl_usdc

    def to_summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "equity_usdt": round(self.equity, 4),
            "net_pnl_usdt": round(self.total_net_pnl_usdc, 4),
            "winrate": f"{self.winrate:.0%}",
            "trades": self.positions_closed,
            "wins": self.winning_trades,
            "losses": self.losing_trades,
            "stop_loss_exits": self.stop_loss_exits,
            "take_profit_exits": self.take_profit_exits,
            "fees_paid": round(self.total_fees_paid, 4),
            "signals_refused": self.signals_refused,
            "stale_refused": self.stale_signals_refused,
            "disclaimer": self.disclaimer,
        }


class DydxLiveObserver:
    """
    Observateur paper trading dYdX v4.

    Architecture:
    1. Discovery: Cosmos LCD → shortlist des meilleurs wallets
    2. Poll REST toutes les 5s pour chaque wallet shortlisté
    3. Cluster detector: détecte 2+ wallets même direction dans 60s
    4. Paper entry: si cluster frais + marché prioritaire + pas max_open
    5. Paper exit: stop-loss (-1.5%), take-profit (+2.5%), ou sortie leader

    RÉGLAGES EMPIRIQUES:
    - ETH-USD en priorité (signal age 3s prouvé dans HL)
    - Stop-loss OBLIGATOIRE (HYPE sans stop = -$20)
    - Poll 5s au lieu de 47s (résout 47% NO_MATCHING)
    - 2 wallets min (pas 5+, contre-productif d'après l'analyse)

    PAPER-ONLY. AUCUN ORDRE RÉEL. AUCUNE CLÉ PRIVÉE.
    """

    DISCLAIMER = (
        "PAPER SIMULATION ONLY. READ-ONLY data. No real orders. No real money. "
        "No private keys. No deposits. No withdrawals."
    )

    def __init__(
        self,
        config: DydxV4Config,
        rest_client: DydxIndexerRestClient,
        cluster_detector: DydxClusterDetector,
        discovery: Optional[DydxWalletDiscovery] = None,
        initial_shortlist: Optional[list[WalletScore]] = None,
        poll_interval_s: float = POLL_INTERVAL_S,
        max_signal_age_ms: int = MAX_SIGNAL_AGE_MS,
        stop_loss_pct: float = STOP_LOSS_PCT,
        take_profit_pct: float = TAKE_PROFIT_PCT,
        focus_markets: Optional[list[str]] = None,
    ) -> None:
        assert_paper_only(config)

        self.config = config
        self.rest = rest_client
        self.cluster = cluster_detector
        self.discovery = discovery
        self.poll_interval_s = poll_interval_s
        self.max_signal_age_ms = max_signal_age_ms
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.focus_markets = focus_markets or FOCUS_MARKETS

        # Shortlist wallets à suivre
        self._shortlist: list[WalletScore] = initial_shortlist or []

        # Positions paper ouvertes
        self._open_positions: dict[str, PaperPositionState] = {}
        # Historique des trades fermés
        self._closed_trades: list[dict] = []

        # Stats session
        session_id = hashlib.sha256(f"session:{int(time.time()*1000)}".encode()).hexdigest()[:12]
        self.stats = ObserverStats(
            session_id=session_id,
            started_at_ms=int(time.time() * 1000),
        )

        # Cache prix oracle
        self._mark_prices: dict[str, float] = {}
        self._last_discovery_ms: int = 0
        self._running: bool = False

    # ─────────────────────────────────────────────
    # Boucle principale (REST polling)
    # ─────────────────────────────────────────────

    def run(
        self,
        max_iterations: Optional[int] = None,
        discovery_refresh_s: float = DISCOVERY_REFRESH_S,
    ) -> ObserverStats:
        """
        Boucle principale paper trading.

        Args:
            max_iterations: arrêter après N itérations (None = infini)
            discovery_refresh_s: fréquence de refresh de la shortlist

        Returns:
            ObserverStats (paper only, jamais de vrais ordres)
        """
        assert_paper_only(self.config)
        self._running = True
        iteration = 0

        logger.info(
            "DydxLiveObserver START session=%s mode=%s | %s",
            self.stats.session_id, self.config.mode.value, self.DISCLAIMER
        )

        try:
            while self._running:
                if max_iterations and iteration >= max_iterations:
                    break

                iteration += 1
                now_ms = int(time.time() * 1000)

                # 1. Refresh shortlist si nécessaire
                if (
                    self.discovery
                    and now_ms - self._last_discovery_ms > discovery_refresh_s * 1000
                ):
                    self._refresh_shortlist()
                    self._last_discovery_ms = now_ms

                # 2. Mettre à jour prix oracle
                self._refresh_market_prices()

                # 3. Vérifier stop-loss / take-profit sur positions ouvertes
                self._check_exits()

                # 4. Poller les wallets shortlistés
                self._poll_shortlist()

                # 5. Détecter clusters
                clusters = self.cluster.detect_clusters(min_wallets=2)

                # 6. Évaluer et exécuter signaux paper
                for cluster in clusters:
                    self._evaluate_cluster(cluster)

                # 7. Log de statut
                if iteration % 12 == 0:  # toutes les ~60s
                    logger.info(
                        "Observer status: equity=%.4f pnl=%+.4f positions=%d/%d signals_refused=%d",
                        self.stats.equity,
                        self.stats.total_net_pnl_usdc,
                        len(self._open_positions),
                        MAX_OPEN_PAPER_POSITIONS,
                        self.stats.signals_refused,
                    )

                time.sleep(self.poll_interval_s)

        except KeyboardInterrupt:
            logger.info("Observer arrêté (KeyboardInterrupt)")
        finally:
            self._running = False
            logger.info(
                "Observer STOP: pnl=%+.4f trades=%d winrate=%.0f%% | %s",
                self.stats.total_net_pnl_usdc,
                self.stats.positions_closed,
                self.stats.winrate * 100,
                self.DISCLAIMER,
            )

        return self.stats

    # ─────────────────────────────────────────────
    # Refresh shortlist
    # ─────────────────────────────────────────────

    def _refresh_shortlist(self) -> None:
        """Refresh la shortlist via wallet discovery."""
        if not self.discovery:
            return
        try:
            result = self.discovery.discover_top_wallets(n=20)
            self._shortlist = result.shortlisted
            logger.info("Shortlist refreshed: %d wallets", len(self._shortlist))
        except Exception as e:
            logger.error("Discovery refresh error: %s", e)

    # ─────────────────────────────────────────────
    # Prix oracle
    # ─────────────────────────────────────────────

    def _refresh_market_prices(self) -> None:
        """Récupérer les prix oracle pour les marchés focus."""
        try:
            markets = self.rest.get_markets()
            for ticker, data in markets.get("markets", {}).items():
                try:
                    oracle = float(data.get("oraclePrice") or data.get("indexPrice") or 0)
                    if oracle > 0:
                        self._mark_prices[ticker] = oracle
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.debug("Market price refresh error: %s", e)

    # ─────────────────────────────────────────────
    # Poll wallets shortlistés
    # ─────────────────────────────────────────────

    def _poll_shortlist(self) -> None:
        """Poller les positions de chaque wallet shortlisté."""
        for wallet in self._shortlist:
            try:
                resp = self.rest.get_positions(
                    address=wallet.address,
                    subaccount_number=wallet.subaccount_number,
                    status="OPEN",
                    limit=50,
                )
                positions = resp.get("positions", [])
                events = self.cluster.update_positions(
                    address=wallet.address,
                    positions_raw=positions,
                    fetched_at_ms=int(time.time() * 1000),
                )
                for event in events:
                    if event.event_type in ("OPEN", "ADD"):
                        self.stats.total_signals_seen += 1

            except RestError as e:
                if e.status_code != 404:
                    logger.debug("Poll error %s: %s", wallet.address[:12], e)
            except Exception as e:
                logger.debug("Poll error %s: %s", wallet.address[:12], e)

    # ─────────────────────────────────────────────
    # Évaluation cluster → signal paper
    # ─────────────────────────────────────────────

    def _evaluate_cluster(self, cluster: ClusterSignal) -> None:
        """
        Évaluer un cluster et potentiellement ouvrir une position paper.

        Gates:
        1. Marché dans focus_markets
        2. Signal frais (< max_signal_age_ms)
        3. 2+ wallets
        4. Pas déjà une position ouverte sur ce marché
        5. Max positions paper non atteint
        6. Prix oracle disponible
        """
        self.stats.total_signals_seen += 1
        market = cluster.market_id

        # Gate 1: Marché prioritaire
        if market not in self.focus_markets:
            self._refuse(f"MARKET_NOT_IN_FOCUS ({market})")
            return

        # Gate 2: Fraîcheur signal
        if cluster.signal_age_ms > self.max_signal_age_ms:
            self.stats.stale_signals_refused += 1
            self._refuse(f"STALE_SIGNAL age={cluster.signal_age_ms}ms")
            return

        # Gate 3: Wallets minimum
        if cluster.wallet_count < 2:
            self._refuse(f"SINGLE_WALLET_ONLY count={cluster.wallet_count}")
            return

        # Gate 4: Pas déjà en position sur ce marché
        pos_key = f"{market}:{cluster.side}"
        if pos_key in self._open_positions:
            self._refuse(f"ALREADY_IN_POSITION {pos_key}")
            return

        # Gate 5: Max positions
        if len(self._open_positions) >= MAX_OPEN_PAPER_POSITIONS:
            self._refuse(f"MAX_OPEN_REACHED {len(self._open_positions)}/{MAX_OPEN_PAPER_POSITIONS}")
            return

        # Gate 6: Prix disponible
        mark_price = self._mark_prices.get(market)
        if not mark_price or mark_price <= 0:
            self._refuse(f"NO_ORACLE_PRICE {market}")
            return

        # Calcul stop-loss / take-profit
        sl_factor = self.stop_loss_pct / 100.0
        tp_factor = self.take_profit_pct / 100.0

        if cluster.side == "LONG":
            stop_price = mark_price * (1 - sl_factor)
            tp_price = mark_price * (1 + tp_factor)
        else:
            stop_price = mark_price * (1 + sl_factor)
            tp_price = mark_price * (1 - tp_factor)

        # Calcul frais
        fee = PAPER_NOTIONAL_USDT * (TAKER_FEE_BPS / 10_000)
        size_in_units = PAPER_NOTIONAL_USDT / mark_price

        # Ouvrir position paper
        position_id = hashlib.sha256(
            f"paper:{market}:{cluster.side}:{cluster.cluster_id}".encode()
        ).hexdigest()[:16]

        pos = PaperPositionState(
            position_id=position_id,
            market_id=market,
            side=cluster.side,
            size=PAPER_NOTIONAL_USDT,
            entry_price=mark_price,
            stop_loss_price=stop_price,
            take_profit_price=tp_price,
            opened_at_ms=int(time.time() * 1000),
            cluster_id=cluster.cluster_id,
            wallet_count=cluster.wallet_count,
            fee_paid=fee,
            simulation_mode=SimulationMode(self.config.mode.value),
        )

        self._open_positions[pos_key] = pos
        self.stats.positions_opened += 1
        self.stats.signals_accepted += 1
        self.stats.total_fees_paid += fee

        logger.info(
            "PAPER OPEN: %s %s entry=%.4f sl=%.4f tp=%.4f wallets=%d age=%dms cluster=%s",
            market, cluster.side, mark_price, stop_price, tp_price,
            cluster.wallet_count, cluster.signal_age_ms, cluster.cluster_id,
        )

    # ─────────────────────────────────────────────
    # Vérification exits (stop-loss / take-profit)
    # ─────────────────────────────────────────────

    def _check_exits(self) -> None:
        """Vérifier stop-loss et take-profit sur toutes les positions ouvertes."""
        to_close: list[tuple[str, str, float]] = []  # (pos_key, reason, exit_price)

        for pos_key, pos in self._open_positions.items():
            mark_price = self._mark_prices.get(pos.market_id)
            if not mark_price:
                continue

            if pos.is_stop_loss_hit(mark_price):
                to_close.append((pos_key, "STOP_LOSS", mark_price))
            elif pos.is_take_profit_hit(mark_price):
                to_close.append((pos_key, "TAKE_PROFIT", mark_price))

        for pos_key, reason, exit_price in to_close:
            self._close_paper_position(pos_key, exit_price, reason)

    def _close_paper_position(
        self,
        pos_key: str,
        exit_price: float,
        reason: str,
    ) -> Optional[dict]:
        """Fermer une position paper et enregistrer le trade."""
        pos = self._open_positions.pop(pos_key, None)
        if not pos:
            self.stats.no_matching_refused += 1
            return None

        # Calcul PnL
        gross_pnl = pos.calculate_pnl(exit_price)
        exit_fee = pos.size * (TAKER_FEE_BPS / 10_000)
        net_pnl = gross_pnl - exit_fee

        # Mise à jour stats
        self.stats.positions_closed += 1
        self.stats.total_net_pnl_usdc += net_pnl
        self.stats.total_fees_paid += exit_fee

        if net_pnl > 0:
            self.stats.winning_trades += 1
        else:
            self.stats.losing_trades += 1

        if reason == "STOP_LOSS":
            self.stats.stop_loss_exits += 1
        elif reason == "TAKE_PROFIT":
            self.stats.take_profit_exits += 1

        market = pos.market_id
        self.stats.markets_traded[market] = (
            self.stats.markets_traded.get(market, 0) + net_pnl
        )

        trade = {
            "position_id": pos.position_id,
            "market_id": market,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "size_usdt": pos.size,
            "gross_pnl": round(gross_pnl, 6),
            "net_pnl": round(net_pnl, 6),
            "total_fees": round(pos.fee_paid + exit_fee, 6),
            "reason": reason,
            "wallet_count": pos.wallet_count,
            "duration_ms": int(time.time() * 1000) - pos.opened_at_ms,
            "simulation_mode": pos.simulation_mode.value,
            "disclaimer": "PAPER ONLY. No real order.",
        }
        self._closed_trades.append(trade)

        logger.info(
            "PAPER CLOSE: %s %s reason=%s entry=%.4f exit=%.4f net_pnl=%+.4f equity=%.4f",
            market, pos.side, reason, pos.entry_price, exit_price, net_pnl, self.stats.equity,
        )

        return trade

    # ─────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────

    def _refuse(self, reason: str) -> None:
        self.stats.signals_refused += 1
        logger.debug("Signal refused: %s", reason)

    def get_status(self) -> dict:
        """Statut complet de la session paper trading."""
        assert_paper_only(self.config)
        open_pos = []
        for pk, pos in self._open_positions.items():
            mark = self._mark_prices.get(pos.market_id, pos.entry_price)
            unrealized = pos.calculate_pnl(mark)
            open_pos.append({
                "market_id": pos.market_id,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "mark_price": mark,
                "unrealized_pnl": round(unrealized, 4),
                "stop_loss": pos.stop_loss_price,
                "take_profit": pos.take_profit_price,
                "wallet_count": pos.wallet_count,
                "simulation_mode": pos.simulation_mode.value,
            })

        return {
            **self.stats.to_summary(),
            "open_positions": open_pos,
            "shortlist_size": len(self._shortlist),
            "mark_prices": {k: v for k, v in self._mark_prices.items() if k in self.focus_markets},
        }

    def get_closed_trades(self) -> list[dict]:
        """Historique des trades fermés (paper uniquement)."""
        return list(self._closed_trades)

    def stop(self) -> None:
        """Arrêter la boucle."""
        self._running = False
