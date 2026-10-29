"""Notification queue: records are written in the caller's transaction (status=queued), then
dispatched after commit. Retries use exponential backoff. Provider acceptance is recorded as
'accepted'; only a delivery report sets 'delivered'."""

import logging
from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import DeliveryStatus, NotificationDelivery
from app.services.sms_providers import provider_for

log = logging.getLogger("stockout.notify")

SMS_MAX_LEN = 459  # 3 concatenated GSM-7 segments


def queue_sms(
    db: Session,
    recipient: str,
    message: str,
    purpose: str,
    dedupe_key: str | None = None,
    alert_id: str | None = None,
    facility_id: str | None = None,
    is_demo: bool = False,
) -> NotificationDelivery | None:
    if dedupe_key:
        existing = db.query(NotificationDelivery).filter_by(dedupe_key=dedupe_key).one_or_none()
        if existing:
            return None
        pending = [o for o in db.new if isinstance(o, NotificationDelivery) and o.dedupe_key == dedupe_key]
        if pending:
            return None
    if len(message) > SMS_MAX_LEN:
        message = message[: SMS_MAX_LEN - 1] + "…"
    d = NotificationDelivery(
        recipient=recipient,
        message=message,
        purpose=purpose,
        dedupe_key=dedupe_key,
        alert_id=alert_id,
        facility_id=facility_id,
        is_demo=is_demo,
        status=DeliveryStatus.QUEUED,
        next_attempt_at=utcnow(),
    )
    db.add(d)
    return d


def attempt_delivery(db: Session, d: NotificationDelivery) -> NotificationDelivery:
    settings = get_settings()
    provider = provider_for(settings, d.recipient)
    d.attempts += 1
    result = provider.send(d.recipient, d.message)
    d.provider = result.provider
    d.provider_status = result.provider_status
    if result.message_id:
        d.provider_message_id = result.message_id
    if result.accepted:
        d.status = DeliveryStatus.SIMULATED if result.simulated else DeliveryStatus.ACCEPTED
        d.failure_reason = None
        d.next_attempt_at = None
    elif result.retryable and d.attempts < settings.sms_max_attempts:
        d.status = DeliveryStatus.RETRYING
        d.failure_reason = result.error
        d.next_attempt_at = utcnow() + timedelta(seconds=settings.sms_retry_base_seconds * (2 ** (d.attempts - 1)))
    else:
        d.status = DeliveryStatus.FAILED
        d.failure_reason = result.error
        d.next_attempt_at = None
    return d


def dispatch_due(db: Session, limit: int = 50) -> int:
    now = utcnow()
    due = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.status.in_([DeliveryStatus.QUEUED, DeliveryStatus.RETRYING]),
            or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= now),
        )
        .order_by(NotificationDelivery.created_at)
        .limit(limit)
        .all()
    )
    for d in due:
        try:
            attempt_delivery(db, d)
        except Exception:  # noqa: BLE001 - never let one message break the batch
            log.exception("delivery attempt crashed for %s", d.id)
            d.status = DeliveryStatus.RETRYING
            d.failure_reason = "Internal error during send"
            d.next_attempt_at = now + timedelta(seconds=60)
        db.commit()
    return len(due)


def dispatch_in_background() -> None:
    db = SessionLocal()
    try:
        dispatch_due(db)
    finally:
        db.close()


AT_DELIVERY_MAP = {
    "success": DeliveryStatus.DELIVERED,
    "failed": DeliveryStatus.FAILED,
    "rejected": DeliveryStatus.FAILED,
    "sent": DeliveryStatus.ACCEPTED,
    "buffered": DeliveryStatus.ACCEPTED,
    "submitted": DeliveryStatus.ACCEPTED,
}


def apply_delivery_report(db: Session, message_id: str, status: str, failure_reason: str | None) -> bool:
    d = db.query(NotificationDelivery).filter_by(provider_message_id=message_id).one_or_none()
    if d is None:
        return False
    new_status = AT_DELIVERY_MAP.get(status.lower())
    if new_status is None:
        return True
    # Terminal states are not downgraded by late or repeated callbacks.
    if d.status in (DeliveryStatus.DELIVERED, DeliveryStatus.FAILED) and new_status == DeliveryStatus.ACCEPTED:
        return True
    d.status = new_status
    d.provider_status = f"DLR: {status}"
    if new_status == DeliveryStatus.DELIVERED:
        d.delivered_at = d.delivered_at or utcnow()
        d.failure_reason = None
    elif new_status == DeliveryStatus.FAILED:
        d.failure_reason = (failure_reason or "Delivery failed")[:255]
    return True
