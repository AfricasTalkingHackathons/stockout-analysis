"""Rule-based stockout early-warning engine.

Rules (thresholds live in system configuration, see runtime_config.py):
  stockout        quantity == 0                                    critical
  low_stock       0 < quantity <= min_threshold                    warning
  early_warning   estimated days remaining < early_warning_days    warning (only with adequate history)
  stale_report    facility has items not updated within fresh_hours info (requests a fresh update)
  expiring        stock expiring within expiry_warning_days         warning
  ripple          several facilities in one county report the same medicine short within a window
                  -> "potential local shortage signal" for investigation (never a confirmed shortage)

One unresolved alert exists per dedupe key; re-triggering updates evidence instead of duplicating.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import utcnow
from app.models import (
    OPEN_ALERT_STATUSES,
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Facility,
    FacilityMembership,
    FacilityStatus,
    InventoryItem,
    Medicine,
    MovementType,
    NotificationSubscription,
    RippleEvidence,
    StockMovement,
    StockReport,
    User,
    UserRole,
    VerificationStatus,
)
from app.services.availability import raw_inventory_status
from app.services.notifications import queue_sms
from app.services.runtime_config import get_config

log = logging.getLogger("stockout.alerts")


def _prefix(is_demo: bool) -> str:
    return "StockOut Alert [DEMO]: " if is_demo else "StockOut Alert: "


def find_open_alert(db: Session, dedupe_key: str) -> Alert | None:
    return (
        db.query(Alert)
        .filter(Alert.dedupe_key == dedupe_key, Alert.status.in_(OPEN_ALERT_STATUSES))
        .order_by(Alert.created_at.desc())
        .first()
    )


def open_alert(db: Session, dedupe_key: str, **fields) -> tuple[Alert, bool]:
    existing = find_open_alert(db, dedupe_key)
    if existing:
        existing.evidence = fields.get("evidence", existing.evidence)
        existing.title = fields.get("title", existing.title)
        existing.severity = fields.get("severity", existing.severity)
        existing.updated_at = utcnow()
        return existing, False
    alert = Alert(dedupe_key=dedupe_key, status=AlertStatus.OPEN, **fields)
    db.add(alert)
    db.flush()
    return alert, True


def auto_resolve(db: Session, dedupe_key: str, note: str) -> Alert | None:
    a = find_open_alert(db, dedupe_key)
    if a:
        a.status = AlertStatus.RESOLVED
        a.resolved_at = utcnow()
        a.resolution_notes = f"Auto-resolved: {note}"
    return a


# ---------------------------------------------------------------- consumption estimate

@dataclass
class ConsumptionEstimate:
    days_remaining: float | None
    avg_daily: float | None
    reason: str
    events: int
    history_days: float


def estimate_days_remaining(db: Session, item: InventoryItem, cfg: dict | None = None,
                            now: datetime | None = None) -> ConsumptionEstimate:
    cfg = cfg or get_config(db)
    now = now or utcnow()
    since = now - timedelta(days=cfg["consumption_window_days"])
    first = (
        db.query(func.min(StockMovement.created_at)).filter(StockMovement.inventory_id == item.id).scalar()
    )
    dispenses = (
        db.query(StockMovement)
        .filter(
            StockMovement.inventory_id == item.id,
            StockMovement.movement_type == MovementType.DISPENSE,
            StockMovement.created_at >= since,
        )
        .all()
    )
    if first is None:
        return ConsumptionEstimate(None, None, "No stock movement history", 0, 0)
    if first.tzinfo is None:
        from datetime import timezone
        first = first.replace(tzinfo=timezone.utc)
    history_days = (now - max(first, since)).total_seconds() / 86400
    events = len(dispenses)
    if history_days < cfg["min_consumption_history_days"] or events < cfg["min_consumption_events"]:
        return ConsumptionEstimate(None, None, "Insufficient dispensing history for a reliable estimate",
                                   events, round(history_days, 1))
    total = sum(-m.quantity_delta for m in dispenses if m.quantity_delta < 0)
    if total <= 0:
        return ConsumptionEstimate(None, 0.0, "No consumption recorded in the window", events, round(history_days, 1))
    avg = total / history_days
    return ConsumptionEstimate(round(item.quantity / avg, 1), round(avg, 2), "ok", events, round(history_days, 1))


# ---------------------------------------------------------------- notification fan-out

def facility_alert_recipients(db: Session, facility_id: str, admins_only: bool = False) -> list[str]:
    q = (
        db.query(FacilityMembership, User)
        .join(User, User.id == FacilityMembership.user_id)
        .filter(FacilityMembership.facility_id == facility_id, FacilityMembership.receive_alerts.is_(True),
                User.is_active.is_(True))
    )
    if admins_only:
        q = q.filter(FacilityMembership.role == UserRole.FACILITY_ADMIN)
    phones = []
    for m, u in q:
        p = m.sms_phone or u.phone
        if p and p not in phones:
            phones.append(p)
    return phones


def system_admin_phones(db: Session) -> list[str]:
    return [u.phone for u in db.query(User).filter(User.role == UserRole.SYSTEM_ADMIN, User.is_active.is_(True))
            if u.phone]


def notify_alert(db: Session, alert: Alert, recipients: list[str], message: str, force: bool = False) -> int:
    cfg = get_config(db)
    now = utcnow()
    cooldown = timedelta(minutes=cfg["alert_notify_cooldown_minutes"])
    if not force and alert.last_notified_at and now - alert.last_notified_at < cooldown:
        return 0
    bucket = int(now.timestamp() // cooldown.total_seconds())
    is_demo = bool(alert.facility.is_demo) if alert.facility else bool(alert.evidence.get("is_demo"))
    n = 0
    for phone in recipients:
        if queue_sms(db, phone, message, purpose=f"alert_{alert.alert_type}",
                     dedupe_key=f"alert:{alert.id}:{phone}:{alert.escalation_level}:{bucket}",
                     alert_id=alert.id, facility_id=alert.facility_id, is_demo=is_demo):
            n += 1
    alert.last_notified_at = now
    return n


# ---------------------------------------------------------------- inventory rules

def evaluate_inventory(db: Session, item: InventoryItem, previous_quantity: int | None = None) -> list[Alert]:
    cfg = get_config(db)
    facility: Facility = item.facility
    medicine: Medicine = item.medicine
    created: list[Alert] = []
    base = dict(facility_id=facility.id, medicine_id=medicine.id, county_id=facility.county_id, inventory_id=item.id)
    unit = item.unit
    name = medicine.display_name

    status = raw_inventory_status(item.quantity, item.min_threshold)
    k_out, k_low, k_ew = f"stockout:{item.id}", f"low:{item.id}", f"early:{item.id}"

    if status == "out_of_stock":
        auto_resolve(db, k_low, "stock reached zero; superseded by stockout alert")
        auto_resolve(db, k_ew, "stock reached zero")
        a, new = open_alert(
            db, k_out, alert_type=AlertType.STOCKOUT, severity=AlertSeverity.CRITICAL,
            title=f"{name} out of stock at {facility.name}",
            evidence={"quantity": 0, "unit": unit, "min_threshold": item.min_threshold,
                      "previous_quantity": previous_quantity, "recorded_at": item.last_updated_at.isoformat()},
            **base,
        )
        if new:
            created.append(a)
            notify_alert(db, a, facility_alert_recipients(db, facility.id),
                         f"{_prefix(facility.is_demo)}{name} is OUT OF STOCK at {facility.name} (0 {unit}). "
                         "Please review replenishment. Acknowledge in the dashboard.")
    else:
        auto_resolve(db, k_out, f"stock recorded as {item.quantity} {unit}")
        if status == "low":
            a, new = open_alert(
                db, k_low, alert_type=AlertType.LOW_STOCK, severity=AlertSeverity.WARNING,
                title=f"{name} low at {facility.name}",
                evidence={"quantity": item.quantity, "unit": unit, "min_threshold": item.min_threshold,
                          "previous_quantity": previous_quantity},
                **base,
            )
            if new:
                created.append(a)
                notify_alert(db, a, facility_alert_recipients(db, facility.id),
                             f"{_prefix(facility.is_demo)}{name} is LOW at {facility.name}: {item.quantity} {unit} "
                             f"(minimum {item.min_threshold}). Please plan replenishment.")
        else:
            auto_resolve(db, k_low, f"stock recorded as {item.quantity} {unit}, above minimum")

        est = estimate_days_remaining(db, item, cfg)
        if status != "out_of_stock" and est.days_remaining is not None and est.days_remaining < cfg["early_warning_days"]:
            a, new = open_alert(
                db, k_ew, alert_type=AlertType.EARLY_WARNING, severity=AlertSeverity.WARNING,
                title=f"{name} may run out in ~{est.days_remaining:g} days at {facility.name}",
                evidence={"quantity": item.quantity, "unit": unit, "avg_daily_consumption": est.avg_daily,
                          "estimated_days_remaining": est.days_remaining, "dispense_events": est.events,
                          "history_days": est.history_days},
                **base,
            )
            if new:
                created.append(a)
                notify_alert(db, a, facility_alert_recipients(db, facility.id),
                             f"{_prefix(facility.is_demo)}{name} at {facility.name} may run out in about "
                             f"{est.days_remaining:g} days at current use. Please plan replenishment.")
        elif est.days_remaining is None or est.days_remaining >= cfg["early_warning_days"]:
            auto_resolve(db, k_ew, "estimated days remaining recovered or estimate unavailable")

    # A fresh update clears the facility's stale-data alert if nothing else is stale.
    _refresh_stale_alert(db, facility, cfg)

    if facility.status == FacilityStatus.APPROVED:
        if status in ("out_of_stock", "low"):
            r = run_ripple(db, medicine.id, facility.county_id, cfg)
            if r:
                created.append(r)
        if status in ("available", "low") and (previous_quantity is None or previous_quantity == 0):
            notify_subscribers(db, item, cfg)
    return created


def notify_subscribers(db: Session, item: InventoryItem, cfg: dict) -> int:
    f, m = item.facility, item.medicine
    now = utcnow()
    cooldown = timedelta(hours=cfg["subscriber_cooldown_hours"])
    subs = db.query(NotificationSubscription).filter(
        NotificationSubscription.medicine_id == m.id,
        NotificationSubscription.county_id == f.county_id,
        NotificationSubscription.is_active.is_(True),
    ).all()
    n = 0
    when = item.last_updated_at.strftime("%d %b %H:%M UTC")
    for s in subs:
        if s.last_notified_at and now - s.last_notified_at < cooldown:
            continue
        msg = (f"{_prefix(f.is_demo)}{m.generic_name} {m.strength} reported available at {f.name}, "
               f"{f.county.name} ({when}). Stock may change. Call {f.phone or 'the facility'} before travelling. "
               "Reply STOP to opt out.")
        if queue_sms(db, s.phone, msg, purpose="availability_update",
                     dedupe_key=f"sub:{s.id}:{item.id}:{int(now.timestamp() // cooldown.total_seconds())}",
                     facility_id=f.id, is_demo=f.is_demo):
            s.last_notified_at = now
            n += 1
    return n


# ---------------------------------------------------------------- ripple engine

def run_ripple(db: Session, medicine_id: str, county_id: int, cfg: dict | None = None,
               now: datetime | None = None) -> Alert | None:
    """Returns the ripple alert if it was newly created."""
    cfg = cfg or get_config(db)
    now = now or utcnow()
    since = now - timedelta(hours=cfg["ripple_window_hours"])
    low_w, unv_w = cfg["ripple_low_stock_weight"], cfg["ripple_unverified_weight"]

    facilities = db.query(Facility).filter(Facility.county_id == county_id,
                                           Facility.status == FacilityStatus.APPROVED).all()
    if not facilities:
        return None
    f_ids = [f.id for f in facilities]
    items = {i.facility_id: i for i in db.query(InventoryItem).filter(
        InventoryItem.medicine_id == medicine_id, InventoryItem.facility_id.in_(f_ids))}
    reports: dict[str, list[StockReport]] = {}
    for r in db.query(StockReport).filter(
        StockReport.medicine_id == medicine_id, StockReport.facility_id.in_(f_ids),
        StockReport.created_at >= since, StockReport.verification_status != VerificationStatus.REJECTED,
    ):
        reports.setdefault(r.facility_id, []).append(r)

    evidence_rows: list[dict] = []
    total_score, counted_facilities, confirmed_out = 0.0, 0, 0
    for f in facilities:
        signals = []
        it = items.get(f.id)
        if it and it.last_updated_at >= since:
            signals.append(dict(source_type="inventory", source_id=it.id,
                                observed_status=raw_inventory_status(it.quantity, it.min_threshold),
                                observed_at=it.last_updated_at,
                                verified=it.verification_status == VerificationStatus.VERIFIED))
        for r in reports.get(f.id, []):
            signals.append(dict(source_type="report", source_id=r.id, observed_status=r.reported_status,
                                observed_at=r.created_at,
                                verified=r.verification_status == VerificationStatus.VERIFIED))
        if not signals:
            continue
        latest_confirmed = max((s for s in signals if s["verified"]), key=lambda s: s["observed_at"], default=None)
        for s in signals:
            status_factor = 1.0 if s["observed_status"] == "out_of_stock" else low_w if s["observed_status"] == "low" else 0.0
            w = status_factor * (1.0 if s["verified"] else unv_w)
            # A newer confirmed "available" record supersedes older shortage signals.
            if latest_confirmed and latest_confirmed["observed_status"] == "available" \
                    and s["observed_at"] <= latest_confirmed["observed_at"]:
                w = 0.0
            s["weight"] = round(w, 2)
            s["counted"] = False
        best = max(signals, key=lambda s: s["weight"])
        if best["weight"] > 0:
            best["counted"] = True  # one facility = one piece of independent evidence
            total_score += best["weight"]
            counted_facilities += 1
            if best["verified"] and best["observed_status"] == "out_of_stock":
                confirmed_out += 1
        for s in signals:
            evidence_rows.append({**s, "facility_id": f.id, "facility_name": f.name})

    triggered = counted_facilities >= cfg["ripple_min_facilities"] and total_score >= cfg["ripple_min_score"]
    key = f"ripple:{medicine_id}:{county_id}"
    existing = find_open_alert(db, key)
    if not triggered and not existing:
        return None

    medicine = db.get(Medicine, medicine_id)
    county_name = facilities[0].county.name
    is_demo = all(f.is_demo for f in facilities if f.id in {e["facility_id"] for e in evidence_rows if e["counted"]}) \
        if evidence_rows else False
    summary = {
        "score": round(total_score, 2),
        "facilities_counted": counted_facilities,
        "confirmed_out_of_stock": confirmed_out,
        "window_hours": cfg["ripple_window_hours"],
        "min_facilities": cfg["ripple_min_facilities"],
        "min_score": cfg["ripple_min_score"],
        "threshold_met": triggered,
        "evaluated_at": now.isoformat(),
        "is_demo": is_demo,
        "interpretation": "Potential local shortage signal for investigation. Not a confirmed regional shortage.",
    }
    severity = AlertSeverity.CRITICAL if confirmed_out >= cfg["ripple_min_facilities"] else AlertSeverity.WARNING
    title = f"Potential local shortage signal: {medicine.display_name} in {county_name}"
    if existing:
        if not triggered:
            existing.evidence = {**summary, "note": "Signal currently below threshold; review before resolving."}
        else:
            existing.evidence, existing.severity = summary, severity
        alert, created = existing, False
    else:
        alert, created = open_alert(db, key, alert_type=AlertType.RIPPLE, severity=severity, title=title,
                                    medicine_id=medicine_id, county_id=county_id, evidence=summary)
    alert.ripple_evidence.clear()
    db.flush()
    for e in evidence_rows:
        alert.ripple_evidence.append(RippleEvidence(
            facility_id=e["facility_id"], source_type=e["source_type"], source_id=e["source_id"],
            observed_status=e["observed_status"], observed_at=e["observed_at"], verified=e["verified"],
            weight=e["weight"], counted=e["counted"]))

    if created:
        recipients = list(system_admin_phones(db))
        for f in facilities:
            for p in facility_alert_recipients(db, f.id, admins_only=True):
                if p not in recipients:
                    recipients.append(p)
        notify_alert(db, alert, recipients,
                     f"{_prefix(is_demo)}Potential local shortage signal for {medicine.generic_name} "
                     f"{medicine.strength} in {county_name}: {counted_facilities} facilities reported low/out "
                     f"in {int(cfg['ripple_window_hours'])}h. Review evidence in the dashboard.")
        log.info("ripple alert created %s", alert.id)
        return alert
    return None


# ---------------------------------------------------------------- periodic checks

def _refresh_stale_alert(db: Session, facility: Facility, cfg: dict, notify: bool = False) -> Alert | None:
    cutoff = utcnow() - timedelta(hours=cfg["fresh_hours"])
    stale = db.query(InventoryItem).filter(InventoryItem.facility_id == facility.id,
                                           InventoryItem.last_updated_at < cutoff).all()
    key = f"stale:{facility.id}"
    if not stale:
        auto_resolve(db, key, "all inventory records updated recently")
        return None
    if facility.status != FacilityStatus.APPROVED:
        return None
    if not notify and not find_open_alert(db, key):
        return None
    a, new = open_alert(
        db, key, alert_type=AlertType.STALE_REPORT, severity=AlertSeverity.INFO,
        title=f"{len(stale)} stock record(s) need a fresh update at {facility.name}",
        facility_id=facility.id, county_id=facility.county_id,
        evidence={"stale_items": [{"inventory_id": i.id, "medicine": i.medicine.display_name,
                                   "last_updated_at": i.last_updated_at.isoformat()} for i in stale[:20]],
                  "count": len(stale), "fresh_hours": cfg["fresh_hours"]},
    )
    if new and notify:
        notify_alert(db, a, facility_alert_recipients(db, facility.id),
                     f"{_prefix(facility.is_demo)}{len(stale)} stock record(s) at {facility.name} have not been "
                     f"updated in {int(cfg['fresh_hours'])}h. Please confirm current stock.")
    return a


def check_stale_reports(db: Session) -> int:
    cfg = get_config(db)
    n = 0
    for f in db.query(Facility).filter(Facility.status == FacilityStatus.APPROVED):
        if _refresh_stale_alert(db, f, cfg, notify=True):
            n += 1
    return n


def check_expiring(db: Session, today: date | None = None) -> int:
    cfg = get_config(db)
    today = today or utcnow().date()
    horizon = today + timedelta(days=cfg["expiry_warning_days"])
    n = 0
    for it in db.query(InventoryItem).filter(InventoryItem.expiry_date.isnot(None),
                                             InventoryItem.expiry_date <= horizon, InventoryItem.quantity > 0):
        expired = it.expiry_date < today
        _, new = open_alert(
            db, f"expiry:{it.id}:{it.expiry_date.isoformat()}", alert_type=AlertType.EXPIRING,
            severity=AlertSeverity.CRITICAL if expired else AlertSeverity.WARNING,
            title=f"{it.medicine.display_name} {'expired' if expired else 'expiring'} {it.expiry_date.isoformat()} "
                  f"at {it.facility.name}",
            facility_id=it.facility_id, medicine_id=it.medicine_id, county_id=it.facility.county_id,
            inventory_id=it.id,
            evidence={"expiry_date": it.expiry_date.isoformat(), "quantity": it.quantity, "unit": it.unit,
                      "batch_number": it.batch_number},
        )
        n += int(new)
    return n


def escalate_alerts(db: Session) -> int:
    cfg = get_config(db)
    cutoff = utcnow() - timedelta(hours=cfg["escalation_after_hours"])
    n = 0
    for a in db.query(Alert).filter(Alert.status == AlertStatus.OPEN, Alert.severity == AlertSeverity.CRITICAL,
                                    Alert.escalation_level == 0, Alert.created_at < cutoff):
        a.escalation_level = 1
        recipients = system_admin_phones(db)
        if a.facility_id:
            recipients += [p for p in facility_alert_recipients(db, a.facility_id, admins_only=True)
                           if p not in recipients]
        notify_alert(db, a, recipients,
                     f"{_prefix(a.facility.is_demo if a.facility else False)}ESCALATION: '{a.title}' has not been "
                     f"acknowledged for {int(cfg['escalation_after_hours'])}h.", force=True)
        n += 1
    return n


def run_periodic_checks(db: Session) -> dict:
    from app.services.pickup import run_due_reminders
    out = {
        "stale": check_stale_reports(db),
        "expiring": check_expiring(db),
        "escalated": escalate_alerts(db),
        "pickup_reminders": run_due_reminders(db),
    }
    db.commit()
    return out


def is_live_sms() -> bool:
    s = get_settings()
    return s.at_configured and not s.sms_force_simulation
