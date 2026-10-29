from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.deps import accessible_facility_ids, require
from app.models import County, Medicine, NotificationDelivery, NotificationSubscription, PickupSchedule, User
from app.ratelimit import sensitive_limit
from app.routers import PageQ, SizeQ, paginate
from app.schemas import SubscriptionIn, TestSmsIn, UnsubscribeIn
from app.serializers import delivery_dict, subscription_dict
from app.services.audit import audit
from app.services.notifications import attempt_delivery, dispatch_in_background, queue_sms

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.post("/test")
def send_test(body: TestSmsIn, user: User = Depends(require("notifications.test")), db: Session = Depends(get_db)):
    d = queue_sms(db, body.phone, body.message, purpose="test")
    db.flush()
    attempt_delivery(db, d)
    audit(db, "notification.test", "notification", d.id, actor=user, details={"status": d.status})
    db.commit()
    return delivery_dict(d)


@router.get("/history")
def history(status: str | None = Query(None, pattern="^(queued|simulated|accepted|delivered|failed|retrying)$"),
            purpose: str | None = None, page: int = PageQ, page_size: int = SizeQ,
            user: User = Depends(require("notifications.view")), db: Session = Depends(get_db)):
    q = db.query(NotificationDelivery)
    ids = accessible_facility_ids(db, user)
    if ids is not None:
        q = q.filter(NotificationDelivery.facility_id.in_(ids or ["-"]))
    if status:
        q = q.filter(NotificationDelivery.status == status)
    if purpose:
        q = q.filter(NotificationDelivery.purpose == purpose)
    return paginate(q.order_by(NotificationDelivery.created_at.desc()), page, page_size, delivery_dict)


@router.post("/subscriptions", status_code=201, dependencies=[Depends(sensitive_limit("subscribe"))])
def subscribe(body: SubscriptionIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    medicine = db.get(Medicine, body.medicine_id)
    county = db.get(County, body.county_id)
    if not medicine or not county:
        raise HTTPException(404, "Medicine or county not found")
    sub = db.query(NotificationSubscription).filter_by(phone=body.phone, medicine_id=body.medicine_id,
                                                       county_id=body.county_id).one_or_none()
    if sub is None:
        sub = NotificationSubscription(phone=body.phone, medicine_id=body.medicine_id, county_id=body.county_id,
                                       consent_source="web")
        db.add(sub)
        db.flush()
    else:
        sub.is_active, sub.unsubscribed_at, sub.consent_at, sub.consent_source = True, None, utcnow(), "web"
    queue_sms(
        db, body.phone,
        f"StockOut Alert: you subscribed to availability alerts for {county.name}. "
        "We will text you when a participating facility reports it available. Reply STOP to opt out.",
        purpose="subscribe_confirm", dedupe_key=f"sub:{sub.id}:confirm")
    db.commit()
    background.add_task(dispatch_in_background)
    return {**subscription_dict(sub),
            "message": "You will receive an SMS when a participating facility in this county reports this medicine "
                       "available. Reply STOP to any alert, or use the unsubscribe form, to opt out."}


@router.post("/unsubscribe", dependencies=[Depends(sensitive_limit("unsubscribe"))])
def unsubscribe(body: UnsubscribeIn, db: Session = Depends(get_db)):
    q = db.query(NotificationSubscription).filter_by(phone=body.phone, is_active=True)
    if body.subscription_id:
        q = q.filter(NotificationSubscription.id == body.subscription_id)
    for s in q:
        s.is_active, s.unsubscribed_at = False, utcnow()
    pq = db.query(PickupSchedule).filter_by(phone=body.phone, is_active=True)
    if body.subscription_id:
        pq = pq.filter(PickupSchedule.id == body.subscription_id)
    for s in pq:
        s.is_active, s.unsubscribed_at = False, utcnow()
    db.commit()
    # Same response whether or not the number had subscriptions, to avoid revealing who is subscribed.
    return {"message": "If this number had active alerts or pickup reminders, they have been stopped."}


@router.get("/subscriptions")
def list_subscriptions(page: int = PageQ, page_size: int = SizeQ, user: User = Depends(require("facility.view_all")),
                       db: Session = Depends(get_db)):
    q = db.query(NotificationSubscription).order_by(NotificationSubscription.consent_at.desc())
    return paginate(q, page, page_size, subscription_dict)
