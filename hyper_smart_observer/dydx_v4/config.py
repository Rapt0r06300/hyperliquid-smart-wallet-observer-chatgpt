"""
Configuration dYdX v4 — valeurs sûres par défaut.

TOUTES les options dangereuses sont désactivées par défaut.
Aucune clé privée, aucun seed, aucune mnemonic n'est demandé.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum
    class StrEnum(str, Enum):
        """Compatibilité Python 3.10."""
        def __str__(self) -> str:
            return self.value



class DydxNetwork(StrEnum):
    TESTNET = "testnet"
    MAINNET = "mainnet"


class DydxMode(StrEnum):
    LIVE = "live"
    BACKTEST = "backtest"
    REPLAY = "replay"
    TEST_FIXTURE = "test_fixture"
    DEMO = "demo"  # mode démo — wallets synthétiques, aucun appel réseau réel


# --------------------------------------------------------------------------- #
# Endpoints publics Indexer (READ-ONLY, pas d'authentification)
# --------------------------------------------------------------------------- #
INDEXER_REST_ENDPOINTS = {
    DydxNetwork.TESTNET: "https://indexer.v4testnet.dydx.exchange",
    DydxNetwork.MAINNET: "https://indexer.dydx.trade",
}

INDEXER_WS_ENDPOINTS = {
    DydxNetwork.TESTNET: "wss://indexer.v4testnet.dydx.exchange/v4/ws",
    DydxNetwork.MAINNET: "wss://indexer.dydx.trade/v4/ws",
}

# Marchés autorisés par défaut (whitelist prudente)
DEFAULT_MARKET_WHITELIST = {
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
}

# Marchés blacklistés (inconnus, illiquides, expérimentaux)
DEFAULT_MARKET_BLACKLIST: set[str] = set()


@dataclass
class DydxV4Config:
    """
    Configuration principale dYdX v4.

    Toutes les valeurs dangereuses sont False par défaut.
    Ne jamais mettre DYDX_ALLOW_TRADING=True en production.
    """

    # --- Activation globale ---
    enabled: bool = False  # DYDX_ENABLED

    # --- Réseau ---
    # Par défaut MAINNET READ-ONLY (Indexer public, pas d'auth).
    # TESTNET n'a quasi aucune activité → 0 wallets → simulation vide.
    network: DydxNetwork = DydxNetwork.MAINNET  # DYDX_NETWORK
    require_testnet: bool = False  # DYDX_REQUIRE_TESTNET

    # --- Safety absolue ---
    read_only: bool = True            # DYDX_READ_ONLY
    paper_only: bool = True           # DYDX_PAPER_ONLY
    allow_trading: bool = False       # DYDX_ALLOW_TRADING — JAMAIS True
    allow_private_key: bool = False   # DYDX_ALLOW_PRIVATE_KEY — JAMAIS True
    allow_node_private_api: bool = False  # DYDX_ALLOW_NODE_PRIVATE_API

    # --- Filtres signaux ---
    max_signal_age_ms: int = 4000       # DYDX_MAX_SIGNAL_AGE_MS
    hard_max_signal_age_ms: int = 8000  # DYDX_HARD_MAX_SIGNAL_AGE_MS
    min_edge_bps: float = 30.0          # DYDX_MIN_EDGE_BPS
    edge_safety_multiplier: float = 3.0  # edge > 3x total_cost_bps

    # --- Paper trading ---
    starting_balance_usdc: float = 1000.0  # DYDX_STARTING_BALANCE_USDC
    max_open_paper_trades: int = 3          # DYDX_MAX_OPEN_PAPER_TRADES
    max_position_pct: float = 0.10          # max 10% de la balance par position
    max_total_exposure_pct: float = 0.30    # max 30% d'exposition totale

    # --- Coûts estimés (bps) ---
    taker_fee_bps: float = 5.0       # frais taker dYdX v4
    maker_fee_bps: float = 2.0       # frais maker dYdX v4
    estimated_spread_bps: float = 3.0
    estimated_slippage_bps: float = 5.0
    estimated_latency_bps: float = 2.0
    copy_degradation_bps: float = 5.0

    # --- Marchés ---
    market_whitelist: set[str] = field(default_factory=lambda: set(DEFAULT_MARKET_WHITELIST))
    market_blacklist: set[str] = field(default_factory=lambda: set(DEFAULT_MARKET_BLACKLIST))

    # --- Réseau / HTTP ---
    rest_timeout_s: float = 8.0
    rest_max_retries: int = 2         # réduit: moins d'attente au démarrage
    rest_backoff_base_s: float = 0.5  # réduit: 0.5s → 1s max
    rest_rate_limit_rps: float = 5.0
    # Health check spécifique — rapide, non-bloquant
    health_check_retries: int = 0     # 0 = une seule tentative, échec → continue
    ws_ping_interval_s: float = 30.0
    ws_reconnect_delay_s: float = 5.0
    ws_max_reconnect_attempts: int = 10

    # --- Base de données ---
    db_path: str = "data/dydx_v4.sqlite3"

    # --- Mode ---
    mode: DydxMode = DydxMode.LIVE
    # demo_mode: injecte des wallets synthétiques si discovery retourne 0 wallets
    # Utile quand le réseau est instable ou le Cosmos LCD inaccessible.
    demo_mode: bool = False  # DYDX_DEMO_MODE

    def __post_init__(self) -> None:
        self._assert_safety()

    def _assert_safety(self) -> None:
        """Lever une erreur si des options dangereuses sont activées."""
        if self.allow_trading:
            raise ValueError(
                "SAFETY VIOLATION: allow_trading=True est interdit. "
                "Ce module est READ-ONLY / PAPER-ONLY uniquement."
            )
        if self.allow_private_key:
            raise ValueError(
                "SAFETY VIOLATION: allow_private_key=True est interdit. "
                "Aucune clé privée, seed ou mnemonic ne doit être utilisé."
            )
        if not self.paper_only:
            raise ValueError(
                "SAFETY VIOLATION: paper_only=False est interdit. "
                "Seuls les paper trades sont autorisés."
            )
        if not self.read_only:
            raise ValueError(
                "SAFETY VIOLATION: read_only=False est interdit."
            )
        # require_testnet est maintenant False par défaut — mainnet READ-ONLY autorisé
        if self.require_testnet and self.network == DydxNetwork.MAINNET:
            raise ValueError(
                "SAFETY VIOLATION: require_testnet=True mais network=mainnet. "
                "Mettre require_testnet=False explicitement pour utiliser mainnet (READ-ONLY seulement)."
            )

    @property
    def indexer_rest_url(self) -> str:
        return INDEXER_REST_ENDPOINTS[self.network]

    @property
    def indexer_ws_url(self) -> str:
        return INDEXER_WS_ENDPOINTS[self.network]

    @property
    def total_round_trip_cost_bps(self) -> float:
        """Coût total aller-retour estimé en bps."""
        return (
            self.taker_fee_bps * 2  # entrée + sortie
            + self.estimated_spread_bps
            + self.estimated_slippage_bps
            + self.estimated_latency_bps
            + self.copy_degradation_bps
        )


def load_config_from_env(base: DydxV4Config | None = None) -> DydxV4Config:
    """
    Charge la configuration depuis les variables d'environnement.
    Les valeurs dangereuses restent bloquées même si l'env les active.
    """
    cfg = base or DydxV4Config()

    def _bool(key: str, default: bool) -> bool:
        v = os.environ.get(key, "").lower()
        if v in ("1", "true", "yes"):
            return True
        if v in ("0", "false", "no"):
            return False
        return default

    def _int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def _float(key: str, default: float) -> float:
        try:
            return float(os.environ.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    # Réseau — MAINNET par défaut (Indexer public READ-ONLY)
    net_str = os.environ.get("DYDX_NETWORK", cfg.network.value).lower()
    if net_str == "testnet":
        network = DydxNetwork.TESTNET
    else:
        network = DydxNetwork.MAINNET  # défaut mainnet

    # demo_mode: activé si DYDX_DEMO_MODE=1 ou si réseau=testnet (pas d'activité)
    demo_env = os.environ.get("DYDX_DEMO_MODE", "").lower()
    demo_mode = demo_env in ("1", "true", "yes") or cfg.demo_mode

    # Construire sans allow_trading ni allow_private_key
    return DydxV4Config(
        enabled=_bool("DYDX_ENABLED", cfg.enabled),
        network=network,
        require_testnet=False,    # TOUJOURS False — mainnet READ-ONLY autorisé
        read_only=True,           # TOUJOURS True — non surchargeable
        paper_only=True,          # TOUJOURS True — non surchargeable
        allow_trading=False,      # TOUJOURS False — non surchargeable
        allow_private_key=False,  # TOUJOURS False — non surchargeable
        allow_node_private_api=False,
        max_signal_age_ms=_int("DYDX_MAX_SIGNAL_AGE_MS", cfg.max_signal_age_ms),
        hard_max_signal_age_ms=_int("DYDX_HARD_MAX_SIGNAL_AGE_MS", cfg.hard_max_signal_age_ms),
        min_edge_bps=_float("DYDX_MIN_EDGE_BPS", cfg.min_edge_bps),
        starting_balance_usdc=_float("DYDX_STARTING_BALANCE_USDC", cfg.starting_balance_usdc),
        max_open_paper_trades=_int("DYDX_MAX_OPEN_PAPER_TRADES", cfg.max_open_paper_trades),
        db_path=os.environ.get("DYDX_DB_PATH", cfg.db_path),
        demo_mode=demo_mode,
    )


# Instance par défaut (safe) — MAINNET READ-ONLY
DEFAULT_CONFIG = DydxV4Config()
