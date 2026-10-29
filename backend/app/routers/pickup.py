from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.deps import accessible_facility_ids, require
from app.models import County, Facility, FacilityStatus, Medicine, PickupSchedule, User
from app.ratelimit import sensitive_limit
from app.schemas import PickupLookupIn, PickupScheduleIn, UnsubscribeIn
from app.services.inventory import DomainError
from app.services.notifications import dispatch_in_background
from app.services.pickup import (
    schedule_dict,
    stop_for_phone,
    today_ke,
    upcoming_demand,
    upsert_schedule,
)

router = APIRouter(prefix="/api/pickup-schedules", tags=["pickup-reminders"])


@router.post("", status_code=201, dependencies=[Depends(sensitive_limit("pickup"))])
def create_schedule(body: PickupScheduleIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    today = today_ke()
    if body.next_pickup_on < today:
        raise DomainError("Next collection date cannot be in the past.", 422, "invalid_date")
    if body.next_pickup_on > today + timedelta(days=180):
        raise DomainError("Next collection date must be within 180 days.", 422, "invalid_date")
    if body.remind_days_before >= body.interval_days:
        raise DomainError("Remind-days-before must be smaller than the collection interval.", 422, "invalid_interval")
    med = db.get(Medicine, body.medicine_id)
    if not med or not med.is_active:
        raise HTTPException(404, "Medicine not found")
    if not db.get(County, body.county_id):
        raise HTTPException(404, "County not found")
    fac = None
    if body.preferred_facility_id:
        fac = db.get(Facility, body.preferred_facility_id)
        if not fac or fac.status != FacilityStatus.APPROVED:
            raise HTTPException(404, "Facility not found")
        if fac.county_id != body.county_id:
            raise DomainError("The selected facility is not in that county.", 422, "facility_county_mismatch")
    s = upsert_schedule(
        db, phone=body.phone, medicine=med, county_id=body.county_id, next_pickup_on=body.next_pickup_on,
        interval_days=body.interval_days, remind_days_before=body.remind_days_before,
        preferred_facility=fac, consent_source="web",
    )
    db.commit()
    db.refresh(s)
    background.add_task(dispatch_in_background)
    return {
        **schedule_dict(s, db),
        "message": "Pickup reminder saved. We will SMS you before the collection date. "
                   "The message will not name the medicine. Reply STOP to opt out. "
                   "This does not reserve stock and is not a medical appointment.",
    }


@router.post("/lookup", dependencies=[Depends(sensitive_limit("pickup_lookup"))])
def lookup(body: PickupLookupIn, db: Session = Depends(get_db)):
    rows = (
        db.query(PickupSchedule)
        .filter_by(phone=body.phone, is_active=True)
        .order_by(PickupSchedule.next_pickup_on)
        .all()
    )
    return {"items": [schedule_dict(s, db) for s in rows]}


@router.post("/cancel", dependencies=[Depends(sensitive_limit("pickup_cancel"))])
def cancel(body: UnsubscribeIn, db: Session = Depends(get_db)):
    q = db.query(PickupSchedule).filter_by(phone=body.phone, is_active=True)
    if body.subscription_id:
        q = q.filter(PickupSchedule.id == body.subscription_id)
    for s in q:
        s.is_active, s.unsubscribed_at = False, utcnow()
    db.commit()
    return {"message": "If this number had pickup reminders, they have been stopped."}


@router.get("/demand")
def demand(horizon_days: int = Query(7, ge=1, le=30), user: User = Depends(require("inventory.view")),
           db: Session = Depends(get_db)):
    ids = accessible_facility_ids(db, user)
    return upcoming_demand(db, ids, horizon_days)
