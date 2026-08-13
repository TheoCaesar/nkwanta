"""Where notifications actually go.

An interface with two implementations, and the interface is the point. Everything
upstream — the outbox, idempotency keys, retries, the circuit breaker — is real and fully
exercised. Only this last adapter is a stub, and it sits behind a port precisely so that
swapping it for a real SMS provider touches nothing else.

Recorded as TD-08: the delivery path is unproven against a real gateway. Every provider
with usable reach in Ghana requires payment and identity verification, neither achievable
inside an examination window.
"""

from __future__ import annotations

import abc
import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field

log = logging.getLogger("nkwanta.gateway")


class GatewayError(Exception):
    """The provider could not be reached, or refused the message."""


@dataclass(frozen=True)
class Message:
    recipient_id: uuid.UUID
    text: str
    idempotency_key: str


class NotificationGateway(abc.ABC):
    """The port. A real SMS or push provider implements this and nothing else changes."""

    @abc.abstractmethod
    async def send(self, message: Message) -> None:
        """Deliver, or raise GatewayError."""


class LoggingGateway(NotificationGateway):
    """The default sink: write it to the log and call it delivered.

    Honest about what it is. The notification row in the database is the real artefact a
    user sees; this exists so the delivery path has an endpoint to exercise.
    """

    def __init__(self) -> None:
        self.sent: list[Message] = []

    async def send(self, message: Message) -> None:
        self.sent.append(message)
        log.info("notify %s: %s", message.recipient_id, message.text)


@dataclass
class ControllableGateway(NotificationGateway):
    """A gateway that can be told to fail, so the circuit breaker can be demonstrated.

    This exists **for the demonstration**, and saying so plainly is better than
    disguising it as resilience engineering. A circuit breaker whose behaviour cannot be
    shown is a paragraph in a document; one that can be tripped live, on request, in
    thirty seconds, is evidence.

    Recorded as debt TD-21 — it must not exist in a real deployment.
    """

    healthy: bool = True
    delivered: list[Message] = field(default_factory=list)
    attempts: int = 0

    async def send(self, message: Message) -> None:
        self.attempts += 1
        if not self.healthy:
            raise GatewayError("gateway is unavailable (deliberately, for demonstration)")
        self.delivered.append(message)
        log.info("notify %s: %s", message.recipient_id, message.text)


# Module-level instance so the admin endpoints and the worker share one gateway and one
# breaker. Replaced wholesale in tests rather than mutated.
_gateway: NotificationGateway = ControllableGateway()


def get_gateway() -> NotificationGateway:
    return _gateway


def set_gateway(gateway: NotificationGateway) -> None:
    global _gateway
    _gateway = gateway
