"""
Découverte et scoring de wallets dYdX v4.

Basé sur l'analyse de 1,482,013 events Hyperliquid:
- ETH-USD = seul coin prouvé rentable (+$9.07 net), signal age moyen 3s
- Signal frais (<4s) = critique pour éviter NO_MATCHING refusals (47% des refus)
- 1-2 wallets de qualité > 7 wallets stale (winrate: 41% vs 10%)

READ-ONLY. Aucun ordre. Aucune clé privée.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from hyper_smart_observer.dydx_v4.cosmos_client import (
    DydxCosmosLcdClient,
    OnChainSubaccount,
    LIQUID_MARKETS,
)
from hyper_smart_observer.dydx_v4.rest_client import DydxIndexerRestClient, RestError

logger = logging.getLogger(__name__)

# Marchés prioritaires prouvés sur l'analyse HL (signal age le plus bas)
PRIORITY_MARKETS = ["ETH-USD", "BTC-USD", "SOL-USD", "TIA-USD"]

# Marchés à éviter (prouvés perdants dans l'analyse ou non supportés dYdX)
BLOCKED_MARKETS = frozenset([
    "CASH:WTI", "CASH:TSLA", "CASH:SILVER", "CASH:GOLD",
    "XYZ:CL", "XYZ:AMD", "XYZ:ORCL", "HYPE", "ZEC",
])

# Scores ETH > BTC > SOL (basé sur PnL prouvé de l'analyse)
MARKET_PRIORITY_SCORE = {
    "ETH-USD": 1.0,
    "BTC-USD": 0.8,
    "SOL-USD": 0.6,
    "TIA-USD": 0.5,
    "AVAX-USD": 0.4,
    "BNB-USD": 0.4,
    "ARB-USD": 0.3,
    "OP-USD": 0.3,
}


@dataclass
class WalletScore:
    """Score d'un wallet pour le copy-trading."""
    address: str
    subaccount_number: int = 0
    usdc_balance: float = 0.0
    open_positions: list[dict] = field(default_factory=list)
    total_score: float = 0.0
    # Métriques Indexer (si disponibles)
    net_pnl_usdc: float = 0.0
    winrate: float = 0.0
    profit_factor: float = 1.0
    trade_count: int = 0
    # Qualité de la découverte
    market_priority_score: float = 0.0
    balance_score: float = 0.0
    position_count_score: float = 0.0
    freshness_score: float = 1.0
    # Métadonnées
    discovered_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_updated_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    source: str = "cosmos_lcd"
    note: str = ""


@dataclass
class DiscoveryResult:
    """Résultat d'un run de découverte."""
    run_id: str
    started_at_ms: int
    finished_at_ms: int
    candidates_scanned: int
    shortlisted: list[WalletScore]
    discovery_method: str = "cosmos_lcd"
    disclaimer: str = (
        "PAPER SIMULATION ONLY. Wallet discovery is READ-ONLY. "
        "No real orders, no real money, no private keys."
    )


class DydxWalletDiscovery:
    """
    Découverte et scoring de wallets dYdX v4.

    Stratégie basée sur l'analyse empirique:
    1. Cosmos LCD → trouver wallets avec positions ouvertes sur marchés prioritaires
    2. Indexer REST → backfill fills et calcul PnL historique
    3. Scorer par: balance, marchés prioritaires, freshness, PnL historique
    4. Retourner shortlist triée pour le live_observer

    READ-ONLY. Pas d'ordre. Pas de clé privée.
    """

    DISCLAIMER = (
        "WALLET DISCOVERY: READ-ONLY. No orders. No real money. Paper simulation."
    )

    def __init__(
        self,
        cosmos_client: DydxCosmosLcdClient,
        rest_client: DydxIndexerRestClient,
        min_usdc_balance: float = 5_000.0,
        max_scan_pages: int = 30,
    ) -> None:
        self.cosmos = cosmos_client
        self.rest = rest_client
        self.min_usdc = min_usdc_balance
        self.max_scan_pages = max_scan_pages

    def discover_top_wallets(self, n: int = 20) -> DiscoveryResult:
        """
        Découvrir les N meilleurs wallets à suivre.

        1. Scan Cosmos LCD (tous les subaccounts avec positions)
        2. Filtrer par balance + marchés prioritaires
        3. Scorer chaque candidat
        4. Retourner top N

        Returns:
            DiscoveryResult avec shortlist (paper-only, jamais d'ordres)
        """
        import hashlib

        started = int(time.time() * 1000)
        run_id = hashlib.sha256(f"discovery:{started}".encode()).hexdigest()[:16]

        logger.info("Wallet discovery START run_id=%s n=%d", run_id, n)

        # 1. Scan on-chain
        candidates: list[OnChainSubaccount] = self.cosmos.scan_subaccounts(
            max_pages=self.max_scan_pages,
            min_usdc=self.min_usdc,
            only_with_positions=True,
        )

        logger.info("Cosmos scan: %d candidats avec positions", len(candidates))

        # 2. Filtrer et scorer
        scored: list[WalletScore] = []
        for sub in candidates:
            ws = self._score_wallet(sub)
            if ws.total_score > 0:
                scored.append(ws)

        # 3. Enrichir top 50 avec données Indexer (fills historiques)
        scored.sort(key=lambda x: x.total_score, reverse=True)
        top_to_enrich = scored[:50]

        for ws in top_to_enrich:
            self._enrich_with_indexer(ws)

        # 4. Re-trier après enrichissement
        scored.sort(key=lambda x: x.total_score, reverse=True)
        shortlist = scored[:n]

        finished = int(time.time() * 1000)
        result = DiscoveryResult(
            run_id=run_id,
            started_at_ms=started,
            finished_at_ms=finished,
            candidates_scanned=len(candidates),
            shortlisted=shortlist,
        )

        logger.info(
            "Discovery DONE run_id=%s candidates=%d shortlisted=%d elapsed_s=%.1f | %s",
            run_id, len(candidates), len(shortlist),
            (finished - started) / 1000, self.DISCLAIMER
        )

        return result

    def _score_wallet(self, sub: OnChainSubaccount) -> WalletScore:
        """Calculer le score initial basé sur les données on-chain seulement."""
        ws = WalletScore(
            address=sub.address,
            subaccount_number=sub.subaccount_number,
            usdc_balance=sub.usdc_balance,
            open_positions=[
                {"market": p.market_id, "side": p.side, "size": p.size}
                for p in sub.positions
            ],
        )

        # Score balance: log scale, capé à 1.0 à $1M
        import math
        ws.balance_score = min(1.0, math.log10(max(1, sub.usdc_balance)) / 6.0)

        # Score marchés prioritaires
        market_scores = []
        for pos in sub.positions:
            market = pos.market_id
            if market in BLOCKED_MARKETS:
                return ws  # score=0 → exclu
            ms = MARKET_PRIORITY_SCORE.get(market, 0.1)
            market_scores.append(ms)

        if not market_scores:
            return ws

        ws.market_priority_score = sum(market_scores) / len(market_scores)

        # Score nb positions (1-3 positions = focus, >5 = diversifié/moins copy-friendly)
        n_pos = sub.total_position_count
        if n_pos == 0:
            ws.position_count_score = 0.0
        elif n_pos <= 3:
            ws.position_count_score = 1.0
        elif n_pos <= 6:
            ws.position_count_score = 0.7
        else:
            ws.position_count_score = 0.4

        # Score total (sans Indexer)
        ws.total_score = (
            0.35 * ws.balance_score +
            0.40 * ws.market_priority_score +
            0.25 * ws.position_count_score
        )
        ws.note = f"on-chain only, balance=${sub.usdc_balance:.0f}, positions={n_pos}"

        return ws

    def _enrich_with_indexer(self, ws: WalletScore) -> None:
        """
        Enrichir un wallet avec ses fills historiques (Indexer REST).
        Met à jour ws.total_score en place.
        """
        try:
            fills_raw = self.rest.paginate_fills(
                address=ws.address,
                subaccount_number=ws.subaccount_number,
                max_pages=5,
                page_size=100,
            )

            if len(fills_raw) < 5:
                ws.note += " | indexer_fills_insufficient"
                return

            # Calcul PnL simplifié depuis fills (même logique que backtest.py)
            pnl_total, fees_total, wins, total = 0.0, 0.0, 0, 0
            open_pos: dict[str, dict] = {}

            for raw in sorted(fills_raw, key=lambda x: x.get("createdAt", "")):
                side = raw.get("side", "")
                market = raw.get("market", "")
                try:
                    price = float(raw.get("price", 0))
                    size = float(raw.get("size", 0))
                    fee = float(raw.get("fee", 0))
                except (ValueError, TypeError):
                    continue

                key = f"{market}"
                if key not in open_pos:
                    if market in BLOCKED_MARKETS:
                        continue
                    open_pos[key] = {
                        "side": "LONG" if side == "BUY" else "SHORT",
                        "entry_price": price, "size": size,
                        "entry_fee": fee,
                    }
                else:
                    pos = open_pos[key]
                    is_close = (
                        (pos["side"] == "LONG" and side == "SELL") or
                        (pos["side"] == "SHORT" and side == "BUY")
                    )
                    if not is_close:
                        # ADD
                        total_notional = pos["size"] * pos["entry_price"] + size * price
                        total_size = pos["size"] + size
                        pos["entry_price"] = total_notional / total_size if total_size > 0 else pos["entry_price"]
                        pos["size"] = total_size
                        pos["entry_fee"] += fee
                    else:
                        # CLOSE
                        gross = (
                            (price - pos["entry_price"]) * pos["size"]
                            if pos["side"] == "LONG"
                            else (pos["entry_price"] - price) * pos["size"]
                        )
                        net = gross - pos["entry_fee"] - fee
                        pnl_total += net
                        fees_total += pos["entry_fee"] + fee
                        total += 1
                        if net > 0:
                            wins += 1
                        del open_pos[key]

            if total >= 3:
                ws.net_pnl_usdc = pnl_total
                ws.trade_count = total
                ws.winrate = wins / total if total > 0 else 0.0

                # Profit factor
                gross_wins = sum(1 for _ in range(wins))  # simplified
                ws.profit_factor = max(0.0, (pnl_total + fees_total) / max(fees_total, 0.01))

                # Bonus PnL positif
                pnl_bonus = min(0.3, max(-0.1, pnl_total / max(abs(pnl_total) + fees_total, 1.0)))

                # Re-score total avec données Indexer
                ws.total_score = (
                    0.25 * ws.balance_score +
                    0.35 * ws.market_priority_score +
                    0.20 * ws.position_count_score +
                    0.20 * (ws.winrate - 0.3) / 0.4 +  # normalised around 0.3-0.7
                    pnl_bonus
                )
                ws.total_score = max(0.0, min(1.0, ws.total_score))
                ws.note += f" | indexer: trades={total} winrate={ws.winrate:.0%} pnl={pnl_total:+.2f}"

        except RestError as e:
            logger.debug("Indexer enrichment error %s: %s", ws.address, e)
        except Exception as e:
            logger.debug("Enrichment error %s: %s", ws.address, e)


def build_seed_shortlist() -> list[WalletScore]:
    """
    Shortlist initiale de wallets connus actifs sur dYdX v4.
    Sert d'amorçage avant la découverte automatique.

    Note: Ces adresses sont issues du scan Cosmos LCD public.
    Aucune donnée privée. READ-ONLY.
    """
    # Adresses découvertes lors du scan initial (juin 2026)
    # Priorité: wallets avec positions sur ETH-USD/BTC-USD et large balance
    SEED_ADDRESSES = [
        # Placeholders - remplacés dynamiquement par discover_top_wallets()
        # Format: (address, note)
    ]
    # Le système remplace cette liste au démarrage via discover_top_wallets()
    return []
