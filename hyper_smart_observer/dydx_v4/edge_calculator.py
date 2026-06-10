"""
Calculateur d'edge dYdX v4 — formule complète du viral bot.

Source: learnwithmeai.com "I Built a Claude Trading Bot That Copies Hyperliquid Millionaires"
        + docs/HYPERSMART_MAGIC_BOT_RESEARCH_20260601.md

Formula:
    edge_remaining_bps =
        leader_expected_edge_bps
        * leader_consistency_factor
        * signal_freshness_score
        * consensus_factor
        - delay_cost_bps
        - spread_bps
        - slippage_bps
        - fee_bps
        - liquidity_penalty_bps
        - adverse_price_move_bps
        - crowding_penalty_bps
        - funding_penalty_bps

Seuil minimum: MIN_EDGE_BPS = 5 (en dessous → NO_TRADE)

PAPER-ONLY. Aucun ordre réel. Aucune clé privée.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Seuils ───────────────────────────────────────────────────────────────────
MIN_EDGE_BPS: float = 5.0           # seuil minimum pour accepter un trade
TAKER_FEE_BPS: float = 5.0         # frais taker dYdX v4 (0.05%)
ROUND_TRIP_FEE_BPS: float = 10.0   # entrée + sortie

# Freshness decay: 1.0 à 0ms, 0.0 à MAX_SIGNAL_AGE_MS
MAX_SIGNAL_AGE_MS: int = 8_000

# Leader edge par défaut si inconnu (bps)
DEFAULT_LEADER_EDGE_BPS: float = 15.0

# Crowding penalty: si >4 wallets identiques → risque de crowding
CROWDING_THRESHOLD: int = 4
CROWDING_PENALTY_BPS: float = 3.0


@dataclass
class EdgeComponents:
    """Décomposition de l'edge pour audit / no-trade logging."""
    leader_expected_edge_bps: float = 0.0
    leader_consistency_factor: float = 1.0
    signal_freshness_score: float = 1.0
    consensus_factor: float = 1.0
    # Coûts (tous positifs = déductibles)
    delay_cost_bps: float = 0.0
    spread_bps: float = 3.0
    slippage_bps: float = 1.0
    fee_bps: float = ROUND_TRIP_FEE_BPS
    liquidity_penalty_bps: float = 0.0
    adverse_price_move_bps: float = 0.0
    crowding_penalty_bps: float = 0.0
    funding_penalty_bps: float = 0.0
    # Résultat
    edge_remaining_bps: float = 0.0
    accepted: bool = False
    reject_reason: str = ""

    @property
    def gross_edge_bps(self) -> float:
        """Edge brut avant coûts."""
        return (
            self.leader_expected_edge_bps
            * self.leader_consistency_factor
            * self.signal_freshness_score
            * self.consensus_factor
        )

    @property
    def total_cost_bps(self) -> float:
        return (
            self.delay_cost_bps
            + self.spread_bps
            + self.slippage_bps
            + self.fee_bps
            + self.liquidity_penalty_bps
            + self.adverse_price_move_bps
            + self.crowding_penalty_bps
            + self.funding_penalty_bps
        )

    def to_notes(self) -> list[str]:
        return [
            f"leader_edge={self.leader_expected_edge_bps:.1f}bps",
            f"freshness={self.signal_freshness_score:.2f}",
            f"consensus={self.consensus_factor:.2f}",
            f"gross={self.gross_edge_bps:.1f}bps",
            f"costs={self.total_cost_bps:.1f}bps",
            f"edge_net={self.edge_remaining_bps:.1f}bps",
            f"accepted={self.accepted}",
        ]


def signal_freshness_score(signal_age_ms: int) -> float:
    """
    Score de fraîcheur du signal.

    1.0 si age = 0ms
    0.8 si age = 1s
    0.5 si age = 3s
    0.2 si age = 6s
    0.0 si age >= 8s
    """
    if signal_age_ms <= 0:
        return 1.0
    if signal_age_ms >= MAX_SIGNAL_AGE_MS:
        return 0.0
    # Décroissance linéaire de 1.0 → 0.0 sur [0, MAX_SIGNAL_AGE_MS]
    return 1.0 - signal_age_ms / MAX_SIGNAL_AGE_MS


def leader_consistency_factor(
    winrate: float,
    profit_factor: float,
    trade_count: int = 0,
) -> float:
    """
    Facteur de confiance dans le leader.

    1.0 si winrate >= 60% et profit_factor >= 2.0
    0.8 si winrate >= 50%
    0.5 si winrate >= 40%
    0.0 si winrate < 40%
    """
    if winrate <= 0 and profit_factor <= 0:
        # Inconnu → facteur conservateur 0.6
        return 0.6

    if winrate >= 0.60 and profit_factor >= 2.0:
        factor = 1.0
    elif winrate >= 0.55:
        factor = 0.9
    elif winrate >= 0.50:
        factor = 0.8
    elif winrate >= 0.45:
        factor = 0.65
    elif winrate >= 0.40:
        factor = 0.5
    else:
        return 0.0

    # Bonus confiance si historique long
    if trade_count >= 50:
        factor = min(1.0, factor * 1.05)
    elif trade_count < 10:
        factor *= 0.8  # pénalité faible historique

    return factor


def consensus_factor(wallet_count: int) -> float:
    """
    Bonus de consensus si plusieurs wallets s'alignent.

    2 wallets = base (1.0)
    3 wallets = +10%
    4 wallets = +15%
    5+ wallets = +18% (cap, risque crowding)
    """
    if wallet_count <= 1:
        return 0.5  # signal trop faible
    if wallet_count == 2:
        return 1.0
    if wallet_count == 3:
        return 1.10
    if wallet_count == 4:
        return 1.15
    return 1.18  # cap à 5+, crowding penalty appliquée séparément


def leader_expected_edge_bps(
    account_score_expectancy_usdc: float = 0.0,
    avg_trade_size_usdc: float = 50.0,
    fallback_bps: float = DEFAULT_LEADER_EDGE_BPS,
) -> float:
    """
    Estimation de l'edge attendu en bps à partir du scoring du leader.

    Si on a l'expectancy historique du leader (PnL net moyen par trade en USDC),
    on la convertit en bps sur la taille notionnelle du paper trade.

    Sans donnée historique, on utilise un fallback conservateur.
    """
    if avg_trade_size_usdc > 0 and account_score_expectancy_usdc != 0:
        # Convertir USDC expectancy en bps
        edge_bps = (account_score_expectancy_usdc / avg_trade_size_usdc) * 10_000
        # Borner entre 0 et 100 bps (au-delà = suspect)
        return max(0.0, min(edge_bps, 100.0))
    return fallback_bps


def calculate_edge(
    signal_age_ms: int,
    wallet_count: int,
    leader_winrate: float = 0.0,
    leader_profit_factor: float = 0.0,
    leader_trade_count: int = 0,
    leader_expectancy_usdc: float = 0.0,
    paper_notional_usdc: float = 50.0,
    spread_bps: float = 3.0,
    slippage_bps: float = 1.0,
    fee_bps: float = ROUND_TRIP_FEE_BPS,
    delay_ms: int = 500,
    liquidity_penalty_bps: float = 0.0,
    adverse_price_move_bps: float = 0.0,
    funding_penalty_bps: float = 0.0,
    min_edge_bps: float = MIN_EDGE_BPS,
) -> EdgeComponents:
    """
    Calculer l'edge net après tous les coûts.

    Returns EdgeComponents avec edge_remaining_bps et accepted.
    """
    result = EdgeComponents(
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
        liquidity_penalty_bps=liquidity_penalty_bps,
        adverse_price_move_bps=adverse_price_move_bps,
        funding_penalty_bps=funding_penalty_bps,
    )

    # 1. Freshness
    result.signal_freshness_score = signal_freshness_score(signal_age_ms)
    if result.signal_freshness_score <= 0.0:
        result.edge_remaining_bps = -999.0
        result.accepted = False
        result.reject_reason = f"STALE_SIGNAL age={signal_age_ms}ms"
        return result

    # 2. Consistency du leader
    result.leader_consistency_factor = leader_consistency_factor(
        leader_winrate, leader_profit_factor, leader_trade_count
    )

    # 3. Edge attendu du leader
    result.leader_expected_edge_bps = leader_expected_edge_bps(
        account_score_expectancy_usdc=leader_expectancy_usdc,
        avg_trade_size_usdc=paper_notional_usdc,
    )

    # 4. Consensus
    result.consensus_factor = consensus_factor(wallet_count)

    # 5. Délai → coût d'adverse selection
    # ~2 bps/seconde de délai sur ETH (volatilité implicite)
    delay_s = delay_ms / 1000.0
    result.delay_cost_bps = min(delay_s * 2.0, 10.0)  # cap 10 bps

    # 6. Crowding penalty
    if wallet_count >= CROWDING_THRESHOLD:
        result.crowding_penalty_bps = CROWDING_PENALTY_BPS

    # 7. Calcul final
    gross = (
        result.leader_expected_edge_bps
        * result.leader_consistency_factor
        * result.signal_freshness_score
        * result.consensus_factor
    )
    result.edge_remaining_bps = gross - result.total_cost_bps

    # 8. Décision
    if result.edge_remaining_bps >= min_edge_bps:
        result.accepted = True
    else:
        result.accepted = False
        result.reject_reason = (
            f"EDGE_TOO_LOW: net={result.edge_remaining_bps:.1f}bps < min={min_edge_bps:.1f}bps"
            f" (gross={gross:.1f}bps - costs={result.total_cost_bps:.1f}bps)"
        )

    logger.debug(
        "edge_calc: age=%dms wallets=%d gross=%.1f costs=%.1f net=%.1f accepted=%s",
        signal_age_ms, wallet_count, gross, result.total_cost_bps,
        result.edge_remaining_bps, result.accepted,
    )
    return result
