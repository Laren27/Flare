"""Alert payload construction and delivery (Ch. 10, Ch. 13 step 5).

Delivery is where `no_socket` stops being theoretical. Selection decides who
*should* hear about an incident; this module finds out who actually can, and
every candidate who cannot is recorded with that reason rather than quietly
dropped (invariant 4).
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SOS, Notification, NotificationStatus
from app.services.websocket_manager import ConnectionRegistry

ALERT_MESSAGE_TYPE = "sos_alert"


@dataclass(frozen=True, slots=True)
class Delivery:
    volunteer_id: int
    delivered: bool


def build_alert_payload(sos: SOS, *, distance_m: float, wave_number: int) -> dict[str, Any]:
    """What a responder's client receives. No victim identity: a responder needs
    the incident, not the person, until they have accepted (Ch. 22)."""
    return {
        "type": ALERT_MESSAGE_TYPE,
        "sos_id": sos.id,
        "lat": sos.lat,
        "lng": sos.lng,
        "description": sos.description,
        "distance_m": round(distance_m, 1),
        "wave_number": wave_number,
        "radius_m": sos.current_radius_m,
        # Present from week 5; null until the AI summary service exists (ADR-013).
        "ai_category": sos.ai_category,
        "ai_priority": sos.ai_priority.value if sos.ai_priority else None,
        "created_at": sos.created_at.isoformat(),
    }


async def deliver_alerts(
    session: AsyncSession,
    *,
    sos: SOS,
    wave_number: int,
    recipients: list[tuple[int, float]],
    registry: ConnectionRegistry,
) -> list[Delivery]:
    """Push the alert to each recipient, recording a Notification row per success.

    `recipients` is (volunteer_id, distance_m). Does not commit -- the caller owns
    the transaction so notifications, dispatch events and incident state land
    together.

    Failures are not retried. A responder whose socket died between selection and
    send is genuinely unreachable right now, and the honest record of that is a
    `no_socket` dispatch event, not an optimistic Notification row claiming an
    alert that nobody received.
    """
    deliveries: list[Delivery] = []

    for volunteer_id, distance_m in recipients:
        payload = build_alert_payload(sos, distance_m=distance_m, wave_number=wave_number)
        delivered = await registry.send(volunteer_id, payload)

        if delivered:
            session.add(
                Notification(
                    sos_id=sos.id,
                    volunteer_id=volunteer_id,
                    wave_number=wave_number,
                    status=NotificationStatus.SENT,
                )
            )

        deliveries.append(Delivery(volunteer_id=volunteer_id, delivered=delivered))

    return deliveries
