"""
Qualité des leaders — n'agir que sur des wallets PROUVÉS gagnants.

READ-ONLY / PAPER-ONLY. Logique pure, testable. Sert la « sélectivité extrême » :
un consensus ne déclenche un paper trade que si assez de wallets participants ont
un historique prouvé (winrate, profit factor, échantillon suffisant). C'est la
version honnête, côté perps, du « peu d'erreurs » — pas une promesse de 98 %.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class LeaderThresholds:
    min_winrate: float = 0.45
    min_profit_factor: float = 1.3
    min_trades: int = 15


def qualifies_as_leader(
    winrate: Optional[float],
    profit_factor: Optional[float],
    trade_count: Optional[int],
    thresholds: Optional[LeaderThresholds] = None,
) -> bool:
    """True si le wallet est un gagnant PROUVÉ (assez de trades + winrate + PF)."""
    t = thresholds or LeaderThresholds()
    if (trade_count or 0) < t.min_trades:
        return False
    if (winrate or 0.0) < t.min_winrate:
        return False
    if (profit_factor or 0.0) < t.min_profit_factor:
        return False
    return True


def has_track_record(wallet: object) -> bool:
    """Le wallet a-t-il des métriques exploitables (≥1 trade mesuré) ?"""
    return (getattr(wallet, "trade_count", 0) or 0) > 0


def count_proven(
    addresses: Iterable[str],
    score_by_addr: dict,
    thresholds: Optional[LeaderThresholds] = None,
) -> int:
    """Compter, parmi `addresses`, les wallets prouvés gagnants (via score_by_addr)."""
    n = 0
    for a in addresses or []:
        w = score_by_addr.get(a)
        if w is None:
            continue
        if qualifies_as_leader(
            getattr(w, "winrate", 0.0),
            getattr(w, "profit_factor", 0.0),
            getattr(w, "trade_count", 0),
            thresholds,
        ):
            n += 1
    return n


def any_track_record(wallets: Iterable[object]) -> bool:
    """Au moins un wallet du lot a-t-il des métriques ? (sinon: ne pas gater)."""
    return any(has_track_record(w) for w in (wallets or []))


__all__ = [
    "LeaderThresholds",
    "qualifies_as_leader",
    "has_track_record",
    "count_proven",
    "any_track_record",
]
