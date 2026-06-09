"""
Client WebSocket Indexer dYdX v4 — READ-ONLY.

- Reconnect automatique
- Resubscribe après reconnexion
- Heartbeat/ping
- Gap detection et recovery REST
- Mode DEGRADED si WS dégradé
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum
    class StrEnum(str, Enum):
        """Compatibilité Python 3.10."""
        def __str__(self) -> str:
            return self.value

from queue import Empty, Queue
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import websocket as _ws_lib
    _WEBSOCKET_AVAILABLE = True
except ImportError:
    _WEBSOCKET_AVAILABLE = False
    logger.warning("websocket-client non disponible — WS client désactivé")


class WsStatus(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    SUBSCRIBED = "SUBSCRIBED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass
class WsMessage:
    """Message WebSocket reçu et normalisé."""
    channel: str
    type: str         # "subscribed", "channel_data", "error", "pong"
    id: Optional[str]
    data: dict
    received_at_ms: int
    raw: str = ""


class DydxIndexerWsClient:
    """
    Client WebSocket Indexer dYdX v4.

    READ-ONLY: écoute uniquement, jamais d'envoi de transaction.
    Reconnect automatique, gap recovery via REST.
    """

    # Canaux supportés
    CHANNEL_MARKETS = "v4_markets"
    CHANNEL_TRADES = "v4_trades"
    CHANNEL_ORDERBOOK = "v4_orderbook"
    CHANNEL_SUBACCOUNTS = "v4_subaccounts"
    CHANNEL_BLOCK_HEIGHT = "v4_block_height"

    def __init__(
        self,
        ws_url: str,
        on_message: Optional[Callable[[WsMessage], None]] = None,
        on_gap_detected: Optional[Callable[[str, str], None]] = None,
        ping_interval_s: float = 30.0,
        reconnect_delay_s: float = 5.0,
        max_reconnect_attempts: int = 10,
    ) -> None:
        self.ws_url = ws_url
        self._on_message_cb = on_message
        self._on_gap_cb = on_gap_detected
        self.ping_interval_s = ping_interval_s
        self.reconnect_delay_s = reconnect_delay_s
        self.max_reconnect_attempts = max_reconnect_attempts

        self._ws: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._status = WsStatus.DISCONNECTED
        self._reconnect_count = 0
        self._last_message_at: float = 0.0
        self._subscriptions: dict[str, dict] = {}  # channel -> params
        self._message_queue: Queue[WsMessage] = Queue(maxsize=10_000)
        self._stop_event = threading.Event()

        # Suivi de séquence pour gap detection
        self._last_sequence: dict[str, int] = {}

    @property
    def status(self) -> WsStatus:
        return self._status

    @property
    def is_healthy(self) -> bool:
        return self._status in (WsStatus.CONNECTED, WsStatus.SUBSCRIBED)

    @property
    def is_degraded(self) -> bool:
        return self._status in (WsStatus.DEGRADED, WsStatus.DISCONNECTED, WsStatus.FAILED)

    def subscribe_markets(self) -> None:
        """S'abonner aux données marché."""
        self._subscriptions[self.CHANNEL_MARKETS] = {
            "type": "subscribe",
            "channel": self.CHANNEL_MARKETS,
            "batched": True,
        }
        self._send_subscription(self.CHANNEL_MARKETS)

    def subscribe_trades(self, market_id: str) -> None:
        """S'abonner aux trades d'un marché."""
        self._subscriptions[f"{self.CHANNEL_TRADES}:{market_id}"] = {
            "type": "subscribe",
            "channel": self.CHANNEL_TRADES,
            "id": market_id,
            "batched": True,
        }
        self._send_subscription(f"{self.CHANNEL_TRADES}:{market_id}")

    def subscribe_orderbook(self, market_id: str) -> None:
        """S'abonner à l'orderbook d'un marché."""
        self._subscriptions[f"{self.CHANNEL_ORDERBOOK}:{market_id}"] = {
            "type": "subscribe",
            "channel": self.CHANNEL_ORDERBOOK,
            "id": market_id,
            "batched": True,
        }
        self._send_subscription(f"{self.CHANNEL_ORDERBOOK}:{market_id}")

    def subscribe_subaccount(self, address: str, subaccount_number: int = 0) -> None:
        """S'abonner aux mises à jour d'un subaccount."""
        key = f"{self.CHANNEL_SUBACCOUNTS}:{address}/{subaccount_number}"
        self._subscriptions[key] = {
            "type": "subscribe",
            "channel": self.CHANNEL_SUBACCOUNTS,
            "id": f"{address}/{subaccount_number}",
        }
        self._send_subscription(key)

    def get_message(self, timeout_s: float = 1.0) -> Optional[WsMessage]:
        """Récupérer le prochain message de la queue."""
        try:
            return self._message_queue.get(timeout=timeout_s)
        except Empty:
            return None

    def start(self) -> None:
        """Démarrer la connexion WebSocket en background."""
        if not _WEBSOCKET_AVAILABLE:
            logger.error("websocket-client non disponible — WS désactivé")
            self._status = WsStatus.FAILED
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="dydx-ws-client"
        )
        self._thread.start()
        logger.info("dYdX WS client démarré: %s", self.ws_url)

    def stop(self) -> None:
        """Arrêter le client WebSocket."""
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._status = WsStatus.DISCONNECTED
        logger.info("dYdX WS client arrêté")

    def _run_loop(self) -> None:
        """Boucle de connexion avec reconnect automatique."""
        while not self._stop_event.is_set():
            try:
                self._status = WsStatus.CONNECTING
                self._reconnect_count += 1

                if self._reconnect_count > self.max_reconnect_attempts:
                    logger.error(
                        "Max reconnect attempts (%d) atteint — WS FAILED",
                        self.max_reconnect_attempts,
                    )
                    self._status = WsStatus.FAILED
                    return

                if _WEBSOCKET_AVAILABLE:
                    import websocket as _ws_lib

                    ws = _ws_lib.WebSocketApp(
                        self.ws_url,
                        on_open=self._on_open,
                        on_message=self._on_raw_message,
                        on_error=self._on_error,
                        on_close=self._on_close,
                        on_ping=self._on_ping,
                        on_pong=self._on_pong,
                    )
                    self._ws = ws
                    ws.run_forever(
                        ping_interval=int(self.ping_interval_s),
                        ping_timeout=10,
                    )

            except Exception as e:
                logger.error("WS run_forever exception: %s", e)

            if self._stop_event.is_set():
                break

            self._status = WsStatus.DEGRADED
            wait = self.reconnect_delay_s * min(self._reconnect_count, 8)
            logger.info(
                "WS reconnect dans %.1fs (tentative %d/%d)",
                wait,
                self._reconnect_count,
                self.max_reconnect_attempts,
            )
            time.sleep(wait)

    def _on_open(self, ws: Any) -> None:
        self._status = WsStatus.CONNECTED
        self._reconnect_count = 0
        self._last_message_at = time.monotonic()
        logger.info("dYdX WS connecté: %s", self.ws_url)
        # Resubscribe à tous les canaux
        for key in list(self._subscriptions.keys()):
            self._send_subscription(key)

    def _on_raw_message(self, ws: Any, raw: str) -> None:
        self._last_message_at = time.monotonic()
        try:
            data = json.loads(raw)
            channel = data.get("channel", "")
            msg_type = data.get("type", "")
            msg_id = data.get("id")
            contents = data.get("contents", {}) or data.get("data", {})

            msg = WsMessage(
                channel=channel,
                type=msg_type,
                id=msg_id,
                data=contents if isinstance(contents, dict) else {"items": contents},
                received_at_ms=int(time.time() * 1000),
                raw=raw,
            )

            # Détection de gap (séquence)
            seq = data.get("messageId") or data.get("sequence")
            if seq and channel:
                key = f"{channel}:{msg_id or ''}"
                last = self._last_sequence.get(key)
                if last is not None and isinstance(seq, int) and seq > last + 1:
                    gap = seq - last - 1
                    logger.warning(
                        "GAP DÉTECTÉ: channel=%s id=%s gap=%d (last=%d current=%d)",
                        channel,
                        msg_id,
                        gap,
                        last,
                        seq,
                    )
                    if self._on_gap_cb:
                        self._on_gap_cb(channel, str(msg_id or ""))
                if isinstance(seq, int):
                    self._last_sequence[f"{channel}:{msg_id or ''}"] = seq

            if msg_type == "subscribed":
                self._status = WsStatus.SUBSCRIBED

            try:
                self._message_queue.put_nowait(msg)
            except Exception:
                pass  # Queue pleine — message perdu (acceptable)

            if self._on_message_cb:
                self._on_message_cb(msg)

        except Exception as e:
            logger.error("WS message parse error: %s | raw=%s...", e, raw[:200])

    def _on_error(self, ws: Any, error: Exception) -> None:
        logger.error("dYdX WS error: %s", error)
        self._status = WsStatus.DEGRADED

    def _on_close(self, ws: Any, close_status_code: Any, close_msg: Any) -> None:
        logger.info(
            "dYdX WS fermé: code=%s msg=%s", close_status_code, close_msg
        )
        self._status = WsStatus.DISCONNECTED

    def _on_ping(self, ws: Any, message: bytes) -> None:
        self._last_message_at = time.monotonic()

    def _on_pong(self, ws: Any, message: bytes) -> None:
        self._last_message_at = time.monotonic()

    def _send_subscription(self, key: str) -> None:
        if not self._ws or self._status not in (WsStatus.CONNECTED, WsStatus.SUBSCRIBED):
            return
        payload = self._subscriptions.get(key)
        if payload:
            try:
                self._ws.send(json.dumps(payload))
                logger.debug("WS subscribed: %s", key)
            except Exception as e:
                logger.error("WS send subscription error: %s", e)

    @property
    def seconds_since_last_message(self) -> float:
        if self._last_message_at == 0:
            return float("inf")
        return time.monotonic() - self._last_message_at


# Type alias pour annotation
Any = object
