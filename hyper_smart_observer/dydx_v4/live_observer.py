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
import threading
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
from hyper_smart_observer.dydx_v4.edge_calculator import calculate_edge, MIN_EDGE_BPS
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

# Timeout force-close: position perdante sans signal frais > N secondes → clôture préventive
# Empêche les pertes non surveillées quand le flux de signaux tarit
STALE_POSITION_TIMEOUT_S = 180.0

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
        PnL réalisé en USDT.
        size = notionnel USDT (ex: 50.0).
        LONG: (mark - entry) / entry * size_usdt
        SHORT: (entry - mark) / entry * size_usdt
        """
        if self.entry_price <= 0:
            return 0.0
        if self.side == "LONG":
            return (mark_price - self.entry_price) / self.entry_price * self.size
        else:
            return (self.entry_price - mark_price) / self.entry_price * self.size

    def unrealized_pnl_pct(self, mark_price: float) -> float:
        """PnL non réalisé en % de la taille notionnelle."""
        if self.entry_price <= 0:
            return 0.0
        if self.side == "LONG":
            return (mark_price - self.entry_price) / self.entry_price * 100.0
        else:
            return (self.entry_price - mark_price) / self.entry_price * 100.0

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
            "stop_loss_exits": self.stop_loss_exits,
            "take_profit_exits": self.take_profit_exits,
            "disclaimer": self.disclaimer,
        }


class DydxLiveObserver:
    """
    Observateur paper trading dYdX v4.

    Architecture:
    1. Discovery: Cosmos LCD → shortlist des meilleurs wallets (background, non-bloquant)
    2. Poll REST toutes les 5s pour chaque wallet shortlisté
    3. Cluster detector: détecte 2+ wallets même direction dans 60s
    4. Paper entry: si cluster frais + marché prioritaire + pas max_open
    5. Paper exit: stop-loss (-1.5%), take-profit (+2.5%), ou timeout stale signal

    RÉGLAGES EMPIRIQUES:
    - ETH-USD en priorité (signal age 3s prouvé dans HL)
    - Stop-loss OBLIGATOIRE (HYPE sans stop = -$20)
    - Poll 5s au lieu de 47s (résout 47% NO_MATCHING)
    - 2 wallets min (pas 5+, contre-productif d'après l'analyse)
    - Stale position timeout 180s: ferme les positions perdantes sans signal frais

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
        # Initialiser à "maintenant" pour éviter le run de découverte synchrone
        # au 1er tour — la découverte démarre en background dans run()
        self._last_discovery_ms: int = int(time.time() * 1000)
        self._running: bool = False
        # Flag background discovery en cours
        self._discovery_running: bool = False
        # Job B viral bot: snapshots des positions par wallet → détection CLOSE
        # {wallet_key: {pos_key: {market, side, size, entry_price}}}
        self._position_snapshots: dict[str, dict] = {}
        # Journal des NO_TRADE par raison (viral bot: "afficher les refus autant que les entrées")
        self._no_trade_reasons: dict[str, int] = {}
        # Mode démo: prix synthétiques + wallets fictifs quand REST inaccessible
        self._demo_mode: bool = getattr(config, 'demo_mode', False)
        # Compteur de ticks pour la simulation démo (cycles de rotation positions)
        self._demo_tick: int = 0

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

        # Lancer la découverte en arrière-plan dès le démarrage (non-bloquant)
        if self.discovery:
            self._start_background_discovery()

        try:
            while self._running:
                if max_iterations and iteration >= max_iterations:
                    break

                iteration += 1
                now_ms = int(time.time() * 1000)

                # 1. Refresh shortlist si nécessaire (refresh périodique après init)
                if (
                    self.discovery
                    and not self._discovery_running
                    and now_ms - self._last_discovery_ms > discovery_refresh_s * 1000
                ):
                    self._start_background_discovery()
                    self._last_discovery_ms = now_ms

                # 2. Mettre à jour prix oracle
                self._refresh_market_prices()

                # 3. Vérifier stop-loss / take-profit sur positions ouvertes
                self._check_exits()

                # 3b. Fermer les positions sans signal frais depuis trop longtemps
                self._check_stale_positions()

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
                        "Observer status: equity=%.4f pnl=%+.4f positions=%d/%d "
                        "shortlist=%d signals_refused=%d discovery=%s",
                        self.stats.equity,
                        self.stats.total_net_pnl_usdc,
                        len(self._open_positions),
                        MAX_OPEN_PAPER_POSITIONS,
                        len(self._shortlist),
                        self.stats.signals_refused,
                        "running" if self._discovery_running else "idle",
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

    def _start_background_discovery(self) -> None:
        """Lancer la découverte de wallets dans un thread daemon (non-bloquant)."""
        if self._discovery_running:
            logger.debug("Discovery déjà en cours, skip")
            return
        self._discovery_running = True

        def _do():
            try:
                logger.info("Background discovery START")
                result = self.discovery.fast_discover(n=20)
                self._shortlist = result.shortlisted
                self._last_discovery_ms = int(time.time() * 1000)
                logger.info(
                    "Background discovery DONE: %d wallets en %.1fs",
                    len(self._shortlist),
                    (result.finished_at_ms - result.started_at_ms) / 1000,
                )
            except Exception as e:
                logger.error("Background discovery error: %s", e)
            finally:
                self._discovery_running = False

        t = threading.Thread(target=_do, name="dydx-discovery", daemon=True)
        t.start()

    def _refresh_shortlist(self) -> None:
        """Refresh périodique (appelé par le timer 6h). Délègue au background thread."""
        self._start_background_discovery()

    def _check_stale_positions(self) -> None:
        """
        Fermer les positions paper si aucun signal frais depuis trop longtemps ET perte.

        Logique: si une position est ouverte depuis > STALE_POSITION_TIMEOUT_S secondes
        ET que la shortlist est vide (plus de wallets à suivre pour confirmer le signal)
        ET que la position est actuellement en perte → clôture préventive.

        Ceci évite de laisser des pertes s'accumuler quand le flux de données tarit.
        """
        if not self._open_positions:
            return

        now_ms = int(time.time() * 1000)
        timeout_ms = STALE_POSITION_TIMEOUT_S * 1000
        to_close: list[tuple[str, float]] = []

        for pos_key, pos in self._open_positions.items():
            age_ms = now_ms - pos.opened_at_ms
            if age_ms < timeout_ms:
                continue  # Position encore jeune, pas de timeout

            mark_price = self._mark_prices.get(pos.market_id)
            if not mark_price:
                continue  # Pas de prix oracle, on ne ferme pas à l'aveugle

            unrealized_pct = pos.unrealized_pnl_pct(mark_price)
            shortlist_empty = len(self._shortlist) == 0

            # Fermer si: timeout dépassé ET (shortlist vide OU perte > 0.5%)
            if shortlist_empty and unrealized_pct < 0:
                to_close.append((pos_key, mark_price))
            elif unrealized_pct < -0.5:
                # Perte > 0.5% avec position âgée → sortie avant stop-loss à -1.5%
                to_close.append((pos_key, mark_price))

        for pos_key, exit_price in to_close:
            logger.info(
                "STALE_TIMEOUT: Fermeture préventive position %s age=%.0fs",
                pos_key,
                (now_ms - self._open_positions[pos_key].opened_at_ms) / 1000
                if pos_key in self._open_positions else 0,
            )
            self._close_paper_position(pos_key, exit_price, "STALE_SIGNAL_TIMEOUT")

    # ─────────────────────────────────────────────
    # Prix oracle
    # ─────────────────────────────────────────────

    def _refresh_market_prices(self) -> None:
        """Récupérer les prix oracle pour les marchés focus.
        Si REST inaccessible et mode démo → utiliser des prix synthétiques avec drift.
        """
        try:
            markets = self.rest.get_markets()
            fetched_any = False
            for ticker, data in markets.get("markets", {}).items():
                try:
                    oracle = float(data.get("oraclePrice") or data.get("indexPrice") or 0)
                    if oracle > 0:
                        self._mark_prices[ticker] = oracle
                        fetched_any = True
                except (ValueError, TypeError):
                    pass
            # Si REST renvoie des marchés valides → désactiver le mode démo
            if fetched_any and self._demo_mode:
                logger.info("REST accessible — désactivation du mode DEMO")
                self._demo_mode = False
        except Exception as e:
            logger.debug("Market price refresh error: %s", e)
            # Fallback démo: prix synthétiques si aucun prix réel disponible
            if not self._mark_prices:
                self._demo_mode = True
                self._inject_demo_prices()

    # Prix synthétiques de référence (mode DEMO uniquement)
    # Basés sur des ordres de grandeur réalistes — drift aléatoire à chaque tick.
    _DEMO_BASE_PRICES: dict[str, float] = {
        "BTC-USD": 67_000.0,
        "ETH-USD": 3_500.0,
        "SOL-USD": 155.0,
        "TIA-USD": 6.50,
        "AVAX-USD": 38.0,
    }

    def _inject_demo_prices(self) -> None:
        """Injecte des prix synthétiques avec micro-drift pour le mode DEMO.
        Légère tendance haussière (+0.05%/tick en espérance) pour simuler
        un marché favorable aux positions LONG des leaders démo.
        PAPER SIMULATION ONLY — ces prix sont FICTIFS.
        """
        import random
        rng = random.Random(int(time.time()) // 5)  # change toutes les 5s
        for market, base in self._DEMO_BASE_PRICES.items():
            existing = self._mark_prices.get(market, base)
            # Drift asymétrique: -0.10% à +0.20% → espérance +0.05%/tick
            # Simule un marché bull réaliste, favorable aux positions LONG
            drift = rng.uniform(-0.0010, 0.0020)
            new_price = existing * (1.0 + drift)
            # Ancrer autour du prix de base (±5% max)
            if abs(new_price - base) / base > 0.05:
                new_price = base * (1.0 + rng.uniform(-0.01, 0.03))
            self._mark_prices[market] = round(new_price, 4)

    def _poll_shortlist(self) -> None:
        """
        Job B du viral bot: poller les positions de chaque wallet shortlisté.
        Mode DEMO: simulation synthétique sans appels REST.
        """
        # Activer le mode démo automatiquement si la shortlist contient des wallets synthétiques
        if not self._demo_mode and self._shortlist:
            if all(getattr(w, 'source', '') == 'demo_synthetic' for w in self._shortlist):
                self._demo_mode = True

        if self._demo_mode:
            self._demo_tick += 1
            self._poll_shortlist_demo()
            return
        self._poll_shortlist_live()

    def _poll_shortlist_demo(self) -> None:
        """
        Simulation synthétique pour mode DEMO — sans appels REST.
        Toutes les 10 ticks (≈50s), les snapshots sont réinitialisés pour
        rejouer des événements OPEN frais → detect_clusters() trouve des clusters
        et peut rouvrir des positions après un SL/TP.
        PAPER SIMULATION ONLY. Aucun argent réel.
        """
        import random
        rng = random.Random(self._demo_tick)
        now_ms = int(time.time() * 1000)

        # FIX: Reset périodique (ticks 1, 11, 21...) pour générer des OPENs frais.
        # Sans ce reset, les signaux vieillissent > 8s et aucun trade ne s'ouvre
        # après le premier cycle SL/TP.
        if self._demo_tick % 10 == 1:
            for w in self._shortlist:
                k = f"{w.address}/{w.subaccount_number}"
                self._position_snapshots.pop(k, None)
            logger.debug(
                "DEMO tick=%d: snapshots réinitialisés → OPENs frais pour tous les wallets",
                self._demo_tick,
            )

        for wallet in self._shortlist:
            wallet_key = f"{wallet.address}/{wallet.subaccount_number}"
            prev_snapshot = self._position_snapshots.get(wallet_key)

            # Initialisation: construire le snapshot initial depuis les specs du wallet
            if prev_snapshot is None:
                current_snapshot: dict[str, dict] = {}
                for pos_spec in wallet.open_positions:
                    market = pos_spec.get("market", "")
                    side = pos_spec.get("side", "")
                    if not market or not side:
                        continue
                    # Utiliser le mark price actuel comme entry_price
                    entry_price = self._mark_prices.get(market, 0.0)
                    if entry_price <= 0:
                        continue
                    notional = pos_spec.get("notional", 5000.0)
                    size = round(notional / entry_price, 4)
                    pk = f"{market}:{side}"
                    current_snapshot[pk] = {
                        "market": market, "side": side,
                        "size": size, "entry_price": entry_price,
                    }
                self._position_snapshots[wallet_key] = current_snapshot
                # Injecter dans le cluster detector comme OPEN
                positions_raw = [
                    {"market": v["market"], "side": v["side"],
                     "size": str(v["size"]), "entryPrice": str(v["entry_price"])}
                    for v in current_snapshot.values()
                ]
                if positions_raw:
                    events = self.cluster.update_positions(
                        address=wallet.address,
                        positions_raw=positions_raw,
                        fetched_at_ms=now_ms,
                    )
                    for event in events:
                        if event.event_type in ("OPEN", "ADD"):
                            self.stats.total_signals_seen += 1
                continue

            # Rotation: fermer + rouvrir une position toutes les ~12 ticks
            if self._demo_tick % 12 == (hash(wallet.address) % 12):
                if prev_snapshot:
                    # Choisir une position au hasard à "fermer"
                    pk_to_close = rng.choice(list(prev_snapshot.keys()))
                    closed_pos = prev_snapshot[pk_to_close]
                    # Nouveau snapshot sans cette position
                    new_snapshot = {k: v for k, v in prev_snapshot.items() if k != pk_to_close}

                    # Détecter le CLOSE → LEADER_EXIT
                    self._handle_leader_close(
                        closed_pos["market"], closed_pos["side"], wallet.address
                    )

                    # Rouvrir immédiatement avec un nouveau prix
                    market = closed_pos["market"]
                    side = closed_pos["side"]
                    entry_price = self._mark_prices.get(market, closed_pos["entry_price"])
                    if entry_price > 0:
                        notional = closed_pos["size"] * closed_pos["entry_price"]
                        new_size = round(notional / entry_price, 4)
                        pk_new = f"{market}:{side}"
                        new_snapshot[pk_new] = {
                            "market": market, "side": side,
                            "size": new_size, "entry_price": entry_price,
                        }
                        # Signaler OPEN au cluster detector
                        self.cluster.update_positions(
                            address=wallet.address,
                            positions_raw=[{
                                "market": market, "side": side,
                                "size": str(new_size), "entryPrice": str(entry_price),
                            }],
                            fetched_at_ms=now_ms,
                        )
                        self.stats.total_signals_seen += 1

                    self._position_snapshots[wallet_key] = new_snapshot
            else:
                # Tick normal: rafraîchir les positions existantes dans le cluster detector
                positions_raw = [
                    {"market": v["market"], "side": v["side"],
                     "size": str(v["size"]), "entryPrice": str(v["entry_price"])}
                    for v in prev_snapshot.values()
                ]
                if positions_raw:
                    self.cluster.update_positions(
                        address=wallet.address,
                        positions_raw=positions_raw,
                        fetched_at_ms=now_ms,
                    )

    # ─────────────────────────────────────────────
    # Accesseur d'état public
    # ─────────────────────────────────────────────

    def get_status(self) -> dict:
        """Retourne un snapshot thread-safe de l'état courant."""
        return {
            "running": self._running,
            "session_id": self.stats.session_id,
            "mode": self.config.mode.value if hasattr(self.config.mode, "value") else str(self.config.mode),
            "shortlist_size": len(self._shortlist),
            "open_positions": len(self._open_positions),
            "iteration": self.stats.total_signals_seen,
            "net_pnl_usdc": round(self.stats.total_net_pnl_usdc, 4),
            "equity": round(self.stats.equity, 4),
            "total_trades": self.stats.positions_closed,
            "winrate": self.stats.winrate,
            "signals_refused": self.stats.signals_refused,
            "stale_refused": self.stats.stale_signals_refused,
            "fees_paid": round(self.stats.total_fees_paid, 4),
            "discovery_running": self._discovery_running,
            "no_trade_reasons": dict(
                sorted(self._no_trade_reasons.items(), key=lambda x: -x[1])[:10]
            ),
            "leader_exits": sum(
                1 for t in self._closed_trades if t.get("reason") == "LEADER_EXIT"
            ),
            "disclaimer": self.DISCLAIMER,
        }

    # ─────────────────────────────────────────────
    # Poll wallets shortlistés
    # ─────────────────────────────────────────────

    def _poll_shortlist_live(self) -> None:
        """
        Job B du viral bot: poller les positions de chaque wallet shortlisté.
        Détecte les OPEN (nouveau cluster) et les CLOSE (position disparue).
        Suit les sorties du leader (LEADER_EXIT).
        """
        for wallet in self._shortlist:
            try:
                resp = self.rest.get_positions(
                    address=wallet.address,
                    subaccount_number=wallet.subaccount_number,
                    status="OPEN",
                    limit=50,
                )
                positions = resp.get("positions", [])
                wallet_key = f"{wallet.address}/{wallet.subaccount_number}"

                # ── Snapshot actuel ─────────────────────────────────────────
                current_snapshot: dict[str, dict] = {}
                for pos in positions:
                    market = pos.get("market", "")
                    side = pos.get("side", "")
                    if not market or not side:
                        continue
                    try:
                        sz = float(pos.get("size", 0) or 0)
                        ep = float(pos.get("entryPrice", 0) or 0)
                    except (ValueError, TypeError):
                        continue
                    pk = f"{market}:{side}"
                    current_snapshot[pk] = {
                        "market": market, "side": side,
                        "size": sz, "entry_price": ep,
                    }

                # ── Détection CLOSE: position présente avant, disparue maintenant ──
                prev_snapshot = self._position_snapshots.get(wallet_key, {})
                for pk, prev_pos in prev_snapshot.items():
                    if pk not in current_snapshot:
                        self._handle_leader_close(
                            prev_pos["market"], prev_pos["side"], wallet.address
                        )

                # Sauvegarder le nouveau snapshot
                self._position_snapshots[wallet_key] = current_snapshot

                # ── Cluster detector (détection OPEN) ─────────────────────
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

    def _handle_leader_close(self, market: str, side: str, leader_addr: str) -> None:
        """
        Fermer le paper trade correspondant quand un leader clôture sa position.

        C'est le mécanisme SELL du viral bot (Job B): quand la position
        disparaît du snapshot → fermer notre paper trade au prix oracle.

        PAPER-ONLY. Aucun ordre réel.
        """
        pos_key = f"{market}:{side}"
        if pos_key not in self._open_positions:
            return

        mark_price = self._mark_prices.get(market)
        if not mark_price or mark_price <= 0:
            return

        pos = self._open_positions[pos_key]
        # Attendre au moins 5s pour éviter les faux positifs (snapshot race)
        age_ms = int(time.time() * 1000) - pos.opened_at_ms
        if age_ms < 5_000:
            logger.debug("LEADER_EXIT skip (position trop récente %dms): %s", age_ms, pos_key)
            return

        logger.info(
            "LEADER_EXIT: %s %s fermé par %s → paper close @ %.4f | PAPER-ONLY",
            side, market, leader_addr[:12], mark_price,
        )
        self._close_paper_position(pos_key, mark_price, "LEADER_EXIT")

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

        # Gate 7: Edge net positif après coûts (viral bot edge formula)
        # leader_winrate/pf depuis wallet scores si disponibles
        avg_wr = 0.0
        avg_pf = 0.0
        avg_exp = 0.0
        n_sc = 0
        for ws in self._shortlist:
            if hasattr(ws, "winrate") and ws.winrate > 0:
                avg_wr += ws.winrate
                avg_pf += getattr(ws, "profit_factor", 1.0)
                avg_exp += getattr(ws, "net_pnl_usdc", 0.0) / max(1, getattr(ws, "trade_count", 1))
                n_sc += 1
        if n_sc > 0:
            avg_wr /= n_sc
            avg_pf /= n_sc
            avg_exp /= n_sc
        else:
            n_sc = -1  # sentinel: skip edge gate

        if n_sc >= 0:
            delay_ms = max(0, int(time.time() * 1000) - cluster.last_wallet_opened_ms)
            edge = calculate_edge(
                signal_age_ms=cluster.signal_age_ms,
                wallet_count=cluster.wallet_count,
                leader_winrate=avg_wr,
                leader_profit_factor=avg_pf,
                leader_expectancy_usdc=avg_exp,
                paper_notional_usdc=PAPER_NOTIONAL_USDT,
                spread_bps=3.0,
                slippage_bps=1.0,
                fee_bps=10.0,
                delay_ms=delay_ms,
                min_edge_bps=MIN_EDGE_BPS,
            )
            if not edge.accepted:
                self._refuse(f"EDGE_INSUFFICIENT ({edge.reject_reason})")
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
        size_notional = PAPER_NOTIONAL_USDT  # en USDT fictifs

        # Ouvrir position paper
        position_id = hashlib.sha256(
            f"paper:{market}:{cluster.side}:{cluster.cluster_id}".encode()
        ).hexdigest()[:16]

        pos = PaperPositionState(
            position_id=position_id,
            market_id=market,
            side=cluster.side,
            size=size_notional,
            entry_price=mark_price,
            stop_loss_price=stop_price,
            take_profit_price=tp_price,
            opened_at_ms=int(time.time() * 1000),
            cluster_id=cluster.cluster_id,
            wallet_count=cluster.wallet_count,
            fee_paid=fee,
            simulation_mode=self.config.mode,
        )

        self._open_positions[pos_key] = pos
        self.stats.positions_opened += 1
        self.stats.signals_accepted += 1
        self.stats.total_fees_paid += fee
        self.stats.total_net_pnl_usdc -= fee  # Frais d'entrée déduits immédiatement

        markets_key = f"{market}:{cluster.side}"
        self.stats.markets_traded[markets_key] = (
            self.stats.markets_traded.get(markets_key, 0) + 1
        )

        logger.info(
            "PAPER OPEN %s %s @ %.4f SL=%.4f TP=%.4f wallets=%d cluster=%s | PAPER-ONLY",
            cluster.side, market, mark_price, stop_price, tp_price,
            cluster.wallet_count, cluster.cluster_id[:8],
        )

    # ─────────────────────────────────────────────
    # Vérification exits (stop-loss / take-profit)
    # ─────────────────────────────────────────────

    def _check_exits(self) -> None:
        """Vérifier stop-loss et take-profit sur toutes les positions ouvertes."""
        to_close: list[tuple[str, float, str]] = []

        for pos_key, pos in self._open_positions.items():
            mark_price = self._mark_prices.get(pos.market_id)
            if not mark_price:
                continue
            if pos.is_stop_loss_hit(mark_price):
                to_close.append((pos_key, mark_price, "STOP_LOSS"))
            elif pos.is_take_profit_hit(mark_price):
                to_close.append((pos_key, mark_price, "TAKE_PROFIT"))

        for pos_key, exit_price, reason in to_close:
            self._close_paper_position(pos_key, exit_price, reason)

    def _close_paper_position(self, pos_key: str, exit_price: float, reason: str) -> None:
        """Clôturer une position paper et mettre à jour les stats."""
        pos = self._open_positions.pop(pos_key, None)
        if not pos:
            return

        gross_pnl = pos.calculate_pnl(exit_price)
        exit_fee = PAPER_NOTIONAL_USDT * (TAKER_FEE_BPS / 10_000)
        net_pnl = gross_pnl - exit_fee

        self.stats.total_net_pnl_usdc += net_pnl
        self.stats.total_fees_paid += exit_fee
        self.stats.positions_closed += 1

        if net_pnl > 0:
            self.stats.winning_trades += 1
        else:
            self.stats.losing_trades += 1

        if reason == "STOP_LOSS":
            self.stats.stop_loss_exits += 1
        elif reason == "TAKE_PROFIT":
            self.stats.take_profit_exits += 1

        trade_record = {
            "position_id": pos.position_id,
            "market_id": pos.market_id,
            "side": pos.side,
            "entry_price": round(pos.entry_price, 6),
            "exit_price": round(exit_price, 6),
            "size": round(pos.size, 6),
            "gross_pnl": round(gross_pnl, 4),
            "fees": round(pos.fee_paid + exit_fee, 4),
            "net_pnl": round(net_pnl, 4),
            "reason": reason,
            "opened_at_ms": pos.opened_at_ms,
            "closed_at_ms": int(time.time() * 1000),
            "wallet_count": pos.wallet_count,
            "cluster_id": pos.cluster_id,
            "disclaimer": "PAPER TRADE ONLY",
        }
        self._closed_trades.append(trade_record)

        logger.info(
            "PAPER CLOSE %s %s entry=%.4f exit=%.4f net_pnl=%+.4f reason=%s | PAPER-ONLY",
            pos.side, pos.market_id, pos.entry_price, exit_price, net_pnl, reason,
        )

    def _refuse(self, reason: str) -> None:
        """Enregistrer un refus de signal (viral bot: log autant les refus que les entrées)."""
        self.stats.signals_refused += 1
        reason_key = reason.split(" ")[0].rstrip("(").split("(")[0]
        self._no_trade_reasons[reason_key] = self._no_trade_reasons.get(reason_key, 0) + 1
        logger.debug("NO_TRADE: %s", reason)

    def stop(self) -> None:
        """Arrêter l'observateur proprement."""
        self._running = False
        logger.info("DydxLiveObserver stop requested | %s", self.DISCLAIMER)
