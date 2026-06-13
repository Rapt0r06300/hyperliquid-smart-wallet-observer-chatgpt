"""
Intégration du scan rapide pour DydxLiveObserver — opt-in, READ-ONLY / PAPER.

Relie `WalletHarvester` (découverte multi-sources) + `FastScanner` (WS temps réel)
au live observer, derrière le flag `DYDX_FAST_SCANNER`.

DÉFAUT OFF : si le flag n'est pas activé, l'observer n'instancie même pas cette
classe et garde EXACTEMENT son comportement REST historique. Aucune régression.

Apport quand activé :
- abonne en WebSocket les wallets shortlistés (et ceux découverts par le harvester) ;
- détecte en < 1 s quels wallets viennent de trader (fills frais) ;
- expose `wallets_that_just_moved()` → l'observer poll ces wallets immédiatement
  au lieu d'attendre l'intervalle (latence 8–58 s → ~1 s).

SÉCURITÉ : aucune méthode d'ordre/signature/dépôt. Lecture, abonnement,
agrégation. Un fill n'est jamais un ordre.
"""

from __future__ import annotations

import logging
from typing import Optional

from hyper_smart_observer.dydx_v4.fast_scanner import DEFAULT_MAX_AGE_MS, FastScanner
from hyper_smart_observer.dydx_v4.wallet_harvester import WalletHarvester

logger = logging.getLogger(__name__)


class FastScanIntegration:
    """Orchestre harvester + scanner pour le live observer (opt-in)."""

    def __init__(
        self,
        ws_client=None,
        max_age_ms: int = DEFAULT_MAX_AGE_MS,
        hot_capacity: int = 500,
        harvester: Optional[WalletHarvester] = None,
    ) -> None:
        self.scanner = FastScanner(
            ws_client=ws_client, max_age_ms=max_age_ms, hot_capacity=hot_capacity
        )
        self.harvester = harvester or WalletHarvester(max_track=hot_capacity)
        self._ws = ws_client
        self._cosmos_enabled = False
        # Brancher la réception WS sur le scanner (READ-ONLY). Le client WS appelle
        # son `_on_message_cb` à chaque message reçu ; on le pointe vers le scanner.
        if ws_client is not None:
            try:
                ws_client._on_message_cb = self.note_ws_message
            except Exception as e:  # pragma: no cover - dépend de l'impl WS
                logger.debug("hook WS échec (ignoré): %s", e)

    # -- Entrée WS ----------------------------------------------------------- #
    def note_ws_message(self, msg) -> None:
        """Pousser un message WS dans le scanner (utilisé par le client WS et les tests)."""
        try:
            self.scanner.handle_ws_message(msg)
        except Exception as e:  # pragma: no cover
            logger.debug("note_ws_message: %s", e)

    # -- Suivi des wallets --------------------------------------------------- #
    def track_shortlist(self, shortlist) -> int:
        """
        Abonner en WS les wallets shortlistés. Accepte des objets de type
        WalletScore (attribut `.address` + `.total_score`). Retourne le nb suivi.
        """
        pairs: list[tuple[str, float]] = []
        for w in shortlist or []:
            addr = getattr(w, "address", None)
            if not isinstance(addr, str) or not addr:
                continue
            score = getattr(w, "total_score", 0.0)
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            pairs.append((addr, score))
        if pairs:
            self.scanner.track_wallets(pairs)
        return len(pairs)

    def track_harvester_top(self, n: Optional[int] = None) -> int:
        """Abonner en WS le top du harvester (découverte multi-sources)."""
        pairs = self.harvester.top_for_scanner(n=n)
        if pairs:
            self.scanner.track_wallets(pairs)
        return len(pairs)

    # -- Découverte on-chain Cosmos (maximum d'adresses) --------------------- #
    def enable_cosmos_discovery(self, cosmos_client, **scan_kwargs) -> None:
        """
        Brancher la source on-chain Cosmos sur le harvester (énumère tous les
        subaccounts dYdX v4 → maximum d'adresses). Idempotent. READ-ONLY.
        """
        if self._cosmos_enabled:
            return
        try:
            self.harvester.add_cosmos_source(cosmos_client, **scan_kwargs)
            self._cosmos_enabled = True
            logger.info("fast_scan: source on-chain Cosmos branchée (READ-ONLY)")
        except Exception as e:  # pragma: no cover
            logger.warning("enable_cosmos_discovery échec (ignoré): %s", e)

    def refresh_discovery(self, n: Optional[int] = None) -> int:
        """
        Passage de découverte (toutes sources, dont Cosmos) puis abonnement du top
        en WS. Renvoie le nb de NOUVELLES adresses. Ne lève jamais (NO_TRADE safe).
        """
        try:
            new = self.harvester.harvest_once()
            self.track_harvester_top(n=n)
            return new
        except Exception as e:  # pragma: no cover
            logger.debug("refresh_discovery: %s", e)
            return 0

    # -- Signal événementiel ------------------------------------------------- #
    def wallets_that_just_moved(self, limit: int = 1000) -> set[str]:
        """
        Adresses uniques ayant produit un fill FRAIS depuis le dernier appel.

        L'observer utilise ce set pour poller immédiatement ces wallets, au lieu
        d'attendre le prochain tick d'intervalle. C'est le gain de latence.
        """
        moved: set[str] = set()
        for fill in self.scanner.drain_fresh(limit=limit):
            moved.add(fill.address)
        return moved

    # -- État ---------------------------------------------------------------- #
    def stats(self) -> dict:
        s = self.scanner.stats()
        s["harvested_addresses"] = len(self.harvester.index)
        s["ws_attached"] = self._ws is not None
        return s


__all__ = ["FastScanIntegration"]
