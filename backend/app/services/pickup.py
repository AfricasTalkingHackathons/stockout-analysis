"""Repeating medicine-collection reminders and refill alternatives.

No diagnosis is stored. Reminder SMS never names the medicine, HIV, TB or any condition.
The product never tells anyone to skip, split or reduce a dose. If the usual facility has no
recent available report, we point to other participating facilities that do.
"""

import re
from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    EAT = ZoneInfo("Africa/Nairobi")
except Exception:  # Windows installs without tzdata
    EAT = timezone(timedelta(hours=3))

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import utcnow
from app.models import Facility, InventoryItem, Medicine, PickupSchedule
from app.services.availability import medicine_dict, raw_inventory_status, search_availability
from app.services.notifications import queue_sms
from app.utils import mask_phone, normalize_ke_phone

# Words that must never appear in a pickup-reminder SMS (privacy + safety).
BANNED_SMS_TERMS = (
    "hiv", "aids", "tb", "tuberculosis", "art", "arv", "antiretroviral", "antitubercular",
    "tenofovir", "dolutegravir", "lamivudine", "rifampicin", "isoniazid", "pyrazinamide",
    "ethambutol", "tld", "rhze",
)


def today_ke(now=None) -> date:
    return (now or utcnow()).astimezone(EAT).date()


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def preferred_status(db: Session, schedule: PickupSchedule) -> dict | None:
    if not schedule.preferred_facility_id:
        return None
    results = search_availability(db, [schedule.medicine], county_id=schedule.county_id, include_unknown=True)
    return next((r for r in results if r["facility"]["id"] == schedule.preferred_facility_id), None)


def alternatives(db: Session, schedule: PickupSchedule, limit: int = 3) -> list[dict]:
    results = search_availability(db, [schedule.medicine], county_id=schedule.county_id, include_unknown=False)
    usable = [r for r in results if r["status"] in ("available", "low")]
    if schedule.preferred_facility_id:
        usable = [r for r in usable if r["facility"]["id"] != schedule.preferred_facility_id]
    return usable[:limit]


def reminder_message(db: Session, schedule: PickupSchedule) -> str:
    """Privacy-safe SMS: date, place, whether to check another facility. No medicine or disease name."""
    demo = "[DEMO] " if schedule.is_demo or get_settings().demo_mode else ""
    when = _fmt(schedule.next_pickup_on)
    pref = preferred_status(db, schedule)
    alts = alternatives(db, schedule, limit=2)

    if schedule.preferred_facility:
        place = schedule.preferred_facility.name
        if schedule.preferred_facility.is_demo:
            demo = "[DEMO] "
    else:
        place = f"a participating facility in {schedule.county.name}"

    ok = pref is not None and pref["status"] in ("available", "low")
    if pref is None and alts:
        ok = True

    if ok:
        stock = "A participating facility has a recent available or low-stock report."
        if pref and pref["status"] == "low":
            stock = "Your selected facility recently reported low stock."
        extra = ""
        if (pref is None or pref["status"] != "available") and alts:
            names = "; ".join(
                f"{r['facility']['name']} ({r['facility']['town'] or r['facility']['county']['name']})"
                for r in alts
            )
            extra = f" Other sites with a recent report: {names}."
        body = (
            f"StockOut Alert {demo}reminder: scheduled medicine pickup on {when} at {place}. {stock}"
            f"{extra} Confirm with the facility before you travel. Do not change how you take your medicine. "
            "Ask a qualified health worker. Reply STOP to stop reminders."
        )
    else:
        extra = ""
        if alts:
            names = "; ".join(
                f"{r['facility']['name']} ({r['facility']['town'] or r['facility']['county']['name']})"
                for r in alts
            )
            extra = f" Other participating facilities with a recent available or low-stock report: {names}."
        else:
            extra = " No participating facility in this county has a recent available report."
        body = (
            f"StockOut Alert {demo}reminder: scheduled medicine pickup on {when}. "
            f"The selected facility has not recently reported this as available.{extra} "
            "Confirm before you travel. Do not skip, split or reduce your dose. Ask a qualified health worker. "
            "Reply STOP to stop reminders."
        )
    if _contains_banned(body):
        body = (
            f"StockOut Alert {demo}reminder: scheduled medicine pickup on {when}. "
            "Confirm stock with a participating facility before you travel. "
            "Do not change how you take your medicine. Reply STOP to stop reminders."
        )
    return body


def _contains_banned(text: str) -> bool:
    low = text.lower()
    for term in BANNED_SMS_TERMS:
        if len(term) <= 3:
            if re.search(rf"\b{re.escape(term)}\b", low):
                return True
        elif term in low:
            return True
    return False


def upsert_schedule(
    db: Session,
    *,
    phone: str,
    medicine: Medicine,
    county_id: int,
    next_pickup_on: date,
    interval_days: int,
    remind_days_before: int,
    preferred_facility: Facility | None,
    consent_source: str,
    is_demo: bool = False,
) -> PickupSchedule:
    phone = normalize_ke_phone(phone) or phone
    existing = db.query(PickupSchedule).filter_by(phone=phone, medicine_id=medicine.id).one_or_none()
    if existing is None:
        existing = PickupSchedule(phone=phone, medicine_id=medicine.id)
        db.add(existing)
    existing.county_id = county_id
    existing.preferred_facility_id = preferred_facility.id if preferred_facility else None
    existing.preferred_facility = preferred_facility
    existing.interval_days = interval_days
    existing.next_pickup_on = next_pickup_on
    existing.remind_days_before = remind_days_before
    existing.is_active = True
    existing.unsubscribed_at = None
    existing.consent_at = utcnow()
    existing.consent_source = consent_source
    existing.is_demo = is_demo or bool(preferred_facility and preferred_facility.is_demo) or get_settings().demo_mode
    existing.last_reminded_for = None
    existing.medicine = medicine
    return existing


def stop_for_phone(db: Session, phone: str) -> int:
    n = 0
    for s in db.query(PickupSchedule).filter_by(phone=phone, is_active=True):
        s.is_active, s.unsubscribed_at = False, utcnow()
        n += 1
    return n


def roll_forward(schedule: PickupSchedule, today: date) -> None:
    if schedule.next_pickup_on >= today:
        return
    # Advance whole intervals so a missed date does not spam daily reminders.
    span = (today - schedule.next_pickup_on).days
    steps = span // schedule.interval_days + 1
    schedule.next_pickup_on = schedule.next_pickup_on + timedelta(days=steps * schedule.interval_days)


def run_due_reminders(db: Session, now=None) -> int:
    today = today_ke(now)
    sent = 0
    rows = (
        db.query(PickupSchedule)
        .options(joinedload(PickupSchedule.medicine), joinedload(PickupSchedule.county),
                 joinedload(PickupSchedule.preferred_facility))
        .filter(PickupSchedule.is_active.is_(True))
        .all()
    )
    for s in rows:
        roll_forward(s, today)
        window_start = s.next_pickup_on - timedelta(days=s.remind_days_before)
        if today < window_start or today > s.next_pickup_on:
            continue
        if s.last_reminded_for == s.next_pickup_on:
            continue
        msg = reminder_message(db, s)
        queued = queue_sms(
            db, s.phone, msg, purpose="pickup_reminder",
            dedupe_key=f"pickup:{s.id}:{s.next_pickup_on.isoformat()}",
            facility_id=s.preferred_facility_id, is_demo=s.is_demo,
        )
        if queued is not None:
            s.last_reminded_at = utcnow()
            s.last_reminded_for = s.next_pickup_on
            sent += 1
    return sent


def schedule_dict(s: PickupSchedule, db: Session | None = None) -> dict:
    pref = preferred_status(db, s) if db is not None else None
    alts = alternatives(db, s) if db is not None else []
    return {
        "id": s.id,
        "phone": mask_phone(s.phone),
        "medicine": medicine_dict(s.medicine),
        "county": {"id": s.county.id, "name": s.county.name},
        "preferred_facility": {
            "id": s.preferred_facility.id,
            "name": s.preferred_facility.name,
            "is_demo": s.preferred_facility.is_demo,
        } if s.preferred_facility else None,
        "interval_days": s.interval_days,
        "next_pickup_on": s.next_pickup_on.isoformat(),
        "remind_days_before": s.remind_days_before,
        "is_active": s.is_active,
        "consent_at": s.consent_at,
        "is_demo": s.is_demo,
        "preferred_status": {
            "status": pref["status"], "status_label": pref["status_label"],
            "last_updated_at": pref["last_updated_at"],
        } if pref else None,
        "alternatives": [
            {
                "facility_id": r["facility"]["id"],
                "name": r["facility"]["name"],
                "town": r["facility"]["town"],
                "status": r["status"],
                "status_label": r["status_label"],
                "last_updated_at": r["last_updated_at"],
                "is_demo": r["facility"]["is_demo"],
            }
            for r in alts
        ],
    }


def upcoming_demand(db: Session, facility_ids: list[str] | None, horizon_days: int = 7) -> dict:
    """Aggregated upcoming collections. No phone numbers or names."""
    today = today_ke()
    until = today + timedelta(days=horizon_days)
    q = (
        db.query(PickupSchedule)
        .options(joinedload(PickupSchedule.medicine), joinedload(PickupSchedule.preferred_facility))
        .filter(PickupSchedule.is_active.is_(True),
                PickupSchedule.next_pickup_on >= today,
                PickupSchedule.next_pickup_on <= until)
    )
    if facility_ids is not None:
        q = q.filter(PickupSchedule.preferred_facility_id.in_(facility_ids or ["-"]))
    rows = q.all()
    grouped: dict[tuple[str, str], dict] = {}
    for s in rows:
        if not s.preferred_facility_id:
            continue
        key = (s.preferred_facility_id, s.medicine_id)
        g = grouped.setdefault(key, {
            "facility_id": s.preferred_facility_id,
            "facility_name": s.preferred_facility.name if s.preferred_facility else None,
            "medicine_id": s.medicine_id,
            "medicine_code": s.medicine.code,
            "medicine_name": s.medicine.display_name,
            "scheduled_pickups": 0,
        })
        g["scheduled_pickups"] += 1

    items = []
    for g in grouped.values():
        inv = db.query(InventoryItem).filter_by(facility_id=g["facility_id"], medicine_id=g["medicine_id"]).one_or_none()
        qty = inv.quantity if inv else None
        status = None
        if inv is not None:
            status = raw_inventory_status(inv.quantity, inv.min_threshold)
        note = None
        if qty is not None and g["scheduled_pickups"] > qty:
            note = ("Last reported quantity may not cover scheduled collections in this window. "
                    "This is a planning prompt only. Stock is not transferred automatically.")
        items.append({**g, "current_quantity": qty, "current_status": status, "note": note})
    items.sort(key=lambda x: (-x["scheduled_pickups"], x["facility_name"] or ""))
    return {
        "horizon_days": horizon_days,
        "from": today.isoformat(),
        "to": until.isoformat(),
        "total_schedules": sum(i["scheduled_pickups"] for i in items),
        "items": items,
        "notice": "Counts are of consented pickup reminders, not confirmed appointments. "
                  "No patient names or phone numbers are included.",
    }
