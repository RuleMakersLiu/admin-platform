import json
from datetime import datetime, timezone
from typing import Any

from app.config import settings


class EventPublisher:
    def __init__(self) -> None:
        self._producer: Any | None = None

    async def start(self) -> None:
        # Keep the metadata-only control plane available while execution is
        # locked. Once the gate opens, Kafka is mandatory and import/startup
        # errors intentionally fail the service startup.
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            enable_idempotence=True,
            acks="all",
            value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        if not self._producer:
            raise RuntimeError("event publisher is unavailable")
        event = {
            "event_version": 1,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        await self._producer.send_and_wait(topic, event, key=key.encode("utf-8"))


publisher = EventPublisher()
