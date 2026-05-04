"""
Internal Event Bus — publishes analytics events to WebSocket clients,
cloud platform (VPS), and configured VMS webhooks.
"""
import asyncio
import time
import httpx
from dataclasses import dataclass, field
from typing import Callable, Any
from loguru import logger


@dataclass
class AnalyticEvent:
    camera_id: int
    analytic_type: str          # epp_detection, fall_detection, etc.
    severity: str               # low | medium | high | critical
    description: str
    confidence: float
    timestamp: float = field(default_factory=time.time)
    snapshot_path: str | None = None
    recording_path: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "analytic_type": self.analytic_type,
            "severity": self.severity,
            "description": self.description,
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp,
            "snapshot_path": self.snapshot_path,
            "recording_path": self.recording_path,
            "metadata": self.metadata,
        }


class EventBus:
    """
    Central event hub. Subscribers receive events async.
    Also forwards events to:
    - WebSocket clients (dashboard)
    - Cloud Platform (VPS) via REST
    - External VMS webhooks (configurable)
    """

    def __init__(self):
        self._subscribers: list[Callable] = []
        self._ws_clients: set = set()
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._cloud_url: str | None = None
        self._cloud_api_key: str | None = None
        self._webhook_urls: list[str] = []
        self._gateway_id: str = "gateway-01"
        self._running = False

    def configure_cloud(self, url: str, api_key: str, gateway_id: str):
        """Configure cloud platform endpoint."""
        self._cloud_url = url.rstrip("/")
        self._cloud_api_key = api_key
        self._gateway_id = gateway_id
        logger.info(f"☁️  Cloud platform configured: {url} (gateway: {gateway_id})")

    def add_webhook(self, url: str):
        """Add external VMS/system webhook."""
        if url not in self._webhook_urls:
            self._webhook_urls.append(url)
            logger.info(f"🔗 Webhook registered: {url}")

    def remove_webhook(self, url: str):
        self._webhook_urls = [u for u in self._webhook_urls if u != url]

    def subscribe(self, callback: Callable):
        """Subscribe an internal handler to receive events."""
        self._subscribers.append(callback)

    def register_ws_client(self, client):
        self._ws_clients.add(client)

    def unregister_ws_client(self, client):
        self._ws_clients.discard(client)

    async def publish(self, event: AnalyticEvent):
        """Queue an event for async processing."""
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event queue full — dropping event")

    async def start(self):
        """Start the event processing loop."""
        self._running = True
        logger.info("📡 Event bus started")
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event bus error: {e}")

    async def _dispatch(self, event: AnalyticEvent):
        payload = event.to_dict()
        payload["gateway_id"] = self._gateway_id

        # 1. Internal subscribers (e.g. DB writer)
        for cb in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")

        # 2. WebSocket broadcast to dashboard
        dead_clients = set()
        for client in self._ws_clients:
            try:
                await client.send_json({"type": "event", "data": payload})
            except Exception:
                dead_clients.add(client)
        self._ws_clients -= dead_clients

        # 3. Forward to Cloud Platform (VPS) — non-blocking
        if self._cloud_url:
            asyncio.create_task(self._send_to_cloud(payload))

        # 4. Forward to VMS webhooks — non-blocking
        for url in self._webhook_urls:
            asyncio.create_task(self._send_webhook(url, payload))

    async def _send_to_cloud(self, payload: dict):
        """POST event to NeoBit Cloud Platform."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self._cloud_url}/api/v1/gateway/events",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._cloud_api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code not in (200, 201):
                    logger.warning(f"Cloud push failed: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Cloud push error: {e}")

    async def _send_webhook(self, url: str, payload: dict):
        """POST event to external VMS webhook (standard JSON format)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "source": "neobit",
                    "version": "1.0",
                    "event": payload,
                })
        except Exception as e:
            logger.warning(f"Webhook {url} error: {e}")

    def stop(self):
        self._running = False


# Global singleton
event_bus = EventBus()
