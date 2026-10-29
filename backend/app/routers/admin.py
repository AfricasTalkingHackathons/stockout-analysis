from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db, utcnow
from app.deps import accessible_facility_ids, assert_facility_access, get_current_user, is_system_admin, require
from app.models import (
    AuditLog,
    Facility,
    FacilityMembership,
    FacilityStatus,
    InventoryItem,
    Medicine,
    User,
    UserRole,
)
from app.routers import PageQ, SizeQ, paginate
from app.schemas import (
    ConfigUpdateIn,
    FacilityPatch,
    MedicineIn,
    MedicinePatch,
    StaffIn,
    StaffPatch,
    StatusChangeIn,
)
from app.security import hash_password
from app.serializers import facility_private_dict, membership_dict
from app.services.alerts import run_periodic_checks, run_ripple
from app.services.audit import audit
from app.services.availability import medicine_dict, medicine_query
from app.services.dashboard import overview
from app.services.notifications import dispatch_due
from app.services.runtime_config import CONFIG_DEFS, get_config, set_config
from app.services.sms_providers import integration_mode

router = APIRouter(tags=["administration"])


# ---------------------------------------------------------------- dashboards

def _ov_params(county_id: int | None = None, facility_id: str | None = None, medicine_id: str | None = None,
               status: str | None = Query(None, pattern="^(available|low|out_of_stock|stale)$"),
               severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
               date_from: datetime | None = None, date_to: datetime | None = None) -> dict:
    return dict(county_id=county_id, facility_id=facility_id, medicine_id=medicine_id, status=status,
                severity=severity, date_from=date_from, date_to=date_to)


@router.get("/api/dashboard/overview")
def dashboard(params: dict = Depends(_ov_params), user: User = Depends(require("inventory.view")),
              db: Session = Depends(get_db)):
    if params["facility_id"]:
        assert_facility_access(db, user, params["facility_id"])
    return overview(db, accessible_facility_ids(db, user), **params)


@router.get("/api/admin/overview")
def admin_overview(params: dict = Depends(_ov_params), user: User = Depends(require("facility.view_all")),
                   db: Session = Depends(get_db)):
    return overview(db, None, include_platform=True, **params)


@router.get("/api/admin/audit-logs")
def audit_logs(action: str | None = None, facility_id: str | None = None, actor: str | None = None,
               date_from: datetime | None = None, date_to: datetime | None = None,
               page: int = PageQ, page_size: int = SizeQ,
               user: User = Depends(require("audit.view")), db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%"))
    if facility_id:
        q = q.filter(AuditLog.facility_id == facility_id)
    if actor:
        q = q.filter(func.lower(AuditLog.actor_label).like(f"%{actor.lower()}%"))
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to)
    return paginate(q.order_by(AuditLog.created_at.desc()), page, page_size, lambda a: {
        "id": a.id, "actor_label": a.actor_label, "action": a.action, "entity_type": a.entity_type,
        "entity_id": a.entity_id, "facility_id": a.facility_id, "details": a.details, "ip_address": a.ip_address,
        "created_at": a.created_at})


@router.get("/api/admin/freshness")
def freshness(user: User = Depends(require("facility.view_all")), db: Session = Depends(get_db)):
    cfg = get_config(db)
    cutoff = utcnow() - timedelta(hours=cfg["fresh_hours"])
    rows = (db.query(Facility.id, Facility.name, Facility.code, Facility.is_demo,
                     func.count(InventoryItem.id), func.min(InventoryItem.last_updated_at),
                     func.max(InventoryItem.last_updated_at))
            .outerjoin(InventoryItem, InventoryItem.facility_id == Facility.id)
            .filter(Facility.status == FacilityStatus.APPROVED).group_by(Facility.id).all())
    stale = dict(db.query(InventoryItem.facility_id, func.count(InventoryItem.id))
                 .filter(InventoryItem.last_updated_at < cutoff).group_by(InventoryItem.facility_id).all())
    from app.database import UTCDateTime  # noqa: F401  (min/max come back naive on SQLite)
    from datetime import timezone

    def aware(v):
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        return v.replace(tzinfo=timezone.utc) if v and v.tzinfo is None else v

    return {"fresh_hours": cfg["fresh_hours"], "facilities": [
        {"facility_id": fid, "name": name, "code": code, "is_demo": demo, "items": n, "stale_items": stale.get(fid, 0),
         "oldest_update": aware(oldest), "latest_update": aware(latest)}
        for fid, name, code, demo, n, oldest, latest in rows]}


# ---------------------------------------------------------------- facilities (private views)

@router.get("/api/manage/facilities")
def manage_facilities(status: str | None = Query(None, pattern="^(pending|approved|suspended|rejected)$"),
                      county_id: int | None = None, page: int = PageQ, page_size: int = SizeQ,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Facility).options(joinedload(Facility.county), joinedload(Facility.location))
    ids = accessible_facility_ids(db, user)
    if ids is not None:
        q = q.filter(Facility.id.in_(ids or ["-"]))
    if status:
        q = q.filter(Facility.status == status)
    if county_id:
        q = q.filter(Facility.county_id == county_id)
    return paginate(q.order_by(Facility.created_at.desc()), page, page_size, facility_private_dict)


@router.get("/api/manage/facilities/{facility_id}")
def manage_facility(facility_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_facility_access(db, user, facility_id)
    f = db.get(Facility, facility_id)
    if not f:
        raise HTTPException(404, "Facility not found")
    return facility_private_dict(f)


@router.patch("/api/manage/facilities/{facility_id}")
def patch_facility(facility_id: str, body: FacilityPatch, user: User = Depends(require("facility.manage")),
                   db: Session = Depends(get_db)):
    assert_facility_access(db, user, facility_id, need_admin=True)
    f = db.get(Facility, facility_id)
    if not f:
        raise HTTPException(404, "Facility not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(f, k, v)
    audit(db, "facility.update", "facility", f.id, actor=user, facility_id=f.id,
          details={k: str(v) for k, v in changes.items()})
    db.commit()
    return facility_private_dict(f)


def _set_status(db: Session, user: User, facility_id: str, status: str, reason: str | None) -> dict:
    f = db.get(Facility, facility_id)
    if not f:
        raise HTTPException(404, "Facility not found")
    old = f.status
    f.status, f.status_reason = status, reason
    if status == FacilityStatus.APPROVED:
        f.approved_at, f.approved_by_id = utcnow(), user.id
    audit(db, f"facility.{status}", "facility", f.id, actor=user, facility_id=f.id,
          details={"from": old, "to": status, "reason": reason})
    db.commit()
    return facility_private_dict(f)


@router.post("/api/admin/facilities/{facility_id}/approve")
def approve(facility_id: str, body: StatusChangeIn | None = None, user: User = Depends(require("facility.approve")),
            db: Session = Depends(get_db)):
    return _set_status(db, user, facility_id, FacilityStatus.APPROVED, body.reason if body else None)


@router.post("/api/admin/facilities/{facility_id}/suspend")
def suspend(facility_id: str, body: StatusChangeIn, user: User = Depends(require("facility.approve")),
            db: Session = Depends(get_db)):
    if not body.reason:
        raise HTTPException(422, "A reason is required to suspend a facility")
    return _set_status(db, user, facility_id, FacilityStatus.SUSPENDED, body.reason)


@router.post("/api/admin/facilities/{facility_id}/reject")
def reject(facility_id: str, body: StatusChangeIn, user: User = Depends(require("facility.approve")),
           db: Session = Depends(get_db)):
    if not body.reason:
        raise HTTPException(422, "A reason is required to reject a registration")
    return _set_status(db, user, facility_id, FacilityStatus.REJECTED, body.reason)


# ---------------------------------------------------------------- staff

@router.get("/api/manage/facilities/{facility_id}/staff")
def list_staff(facility_id: str, user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    assert_facility_access(db, user, facility_id)
    rows = (db.query(FacilityMembership).options(joinedload(FacilityMembership.user))
            .filter_by(facility_id=facility_id).order_by(FacilityMembership.created_at).all())
    return [membership_dict(m) for m in rows]


@router.post("/api/manage/facilities/{facility_id}/staff", status_code=201)
def add_staff(facility_id: str, body: StaffIn, user: User = Depends(require("staff.manage")),
              db: Session = Depends(get_db)):
    assert_facility_access(db, user, facility_id, need_admin=True)
    if not db.get(Facility, facility_id):
        raise HTTPException(404, "Facility not found")
    email = body.email.lower()
    target = db.query(User).filter_by(email=email).one_or_none()
    if target is None:
        target = User(email=email, full_name=body.full_name, phone=body.phone,
                      password_hash=hash_password(body.password), role=body.role)
        db.add(target)
        db.flush()
    elif target.role == UserRole.SYSTEM_ADMIN:
        raise HTTPException(422, "System administrators cannot be added as facility staff")
    if db.query(FacilityMembership).filter_by(user_id=target.id, facility_id=facility_id).first():
        raise HTTPException(409, "This person is already a member of the facility")
    if body.role == UserRole.FACILITY_ADMIN and target.role == UserRole.FACILITY_STAFF:
        target.role = UserRole.FACILITY_ADMIN
    m = FacilityMembership(user_id=target.id, facility_id=facility_id, role=body.role,
                           can_update_stock=body.can_update_stock, sms_phone=body.sms_phone)
    db.add(m)
    audit(db, "staff.add", "membership", None, actor=user, facility_id=facility_id,
          details={"email": email, "role": body.role})
    db.commit()
    db.refresh(m)
    return membership_dict(m)


@router.patch("/api/manage/facilities/{facility_id}/staff/{membership_id}")
def patch_staff(facility_id: str, membership_id: str, body: StaffPatch, user: User = Depends(require("staff.manage")),
                db: Session = Depends(get_db)):
    assert_facility_access(db, user, facility_id, need_admin=True)
    m = db.query(FacilityMembership).filter_by(id=membership_id, facility_id=facility_id).one_or_none()
    if not m:
        raise HTTPException(404, "Staff member not found")
    changes = body.model_dump(exclude_unset=True)
    if m.user_id == user.id and (changes.get("is_active") is False or changes.get("role") == "facility_staff"):
        raise HTTPException(422, "You cannot remove your own administrator access")
    for k in ("role", "can_update_stock", "sms_phone", "receive_alerts"):
        if k in changes:
            setattr(m, k, changes[k])
    if "is_active" in changes:
        m.user.is_active = changes["is_active"]
    if changes.get("role") == UserRole.FACILITY_ADMIN and m.user.role == UserRole.FACILITY_STAFF:
        m.user.role = UserRole.FACILITY_ADMIN
    audit(db, "staff.update", "membership", m.id, actor=user, facility_id=facility_id,
          details={k: str(v) for k, v in changes.items()})
    db.commit()
    return membership_dict(m)


# ---------------------------------------------------------------- catalog

@router.get("/api/admin/medicines")
def admin_medicines(q: str | None = None, page: int = PageQ, page_size: int = SizeQ,
                    user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    return paginate(medicine_query(db, q, include_inactive=is_system_admin(user)), page, page_size,
                    lambda m: {**medicine_dict(m), "is_active": m.is_active})


@router.post("/api/admin/medicines", status_code=201)
def create_medicine(body: MedicineIn, user: User = Depends(require("catalog.manage")), db: Session = Depends(get_db)):
    if db.query(Medicine).filter_by(code=body.code).first():
        raise HTTPException(409, "Medicine code already exists")
    dup = db.query(Medicine).filter(func.lower(Medicine.generic_name) == body.generic_name.lower(),
                                    func.lower(Medicine.strength) == body.strength.lower(),
                                    func.lower(Medicine.dosage_form) == body.dosage_form.lower()).first()
    if dup:
        raise HTTPException(409, f"Same generic, strength and form already exists as {dup.code}")
    m = Medicine(code=body.code, generic_name=body.generic_name.strip(), brand_names=",".join(body.brand_names),
                 strength=body.strength, dosage_form=body.dosage_form.lower(), base_unit=body.base_unit.lower(),
                 category=body.category, requires_prescription=body.requires_prescription,
                 is_long_term=body.is_long_term)
    db.add(m)
    audit(db, "catalog.create", "medicine", None, actor=user, details={"code": body.code})
    db.commit()
    return medicine_dict(m)


@router.patch("/api/admin/medicines/{medicine_id}")
def patch_medicine(medicine_id: str, body: MedicinePatch, user: User = Depends(require("catalog.manage")),
                   db: Session = Depends(get_db)):
    m = db.get(Medicine, medicine_id)
    if not m:
        raise HTTPException(404, "Medicine not found")
    changes = body.model_dump(exclude_unset=True)
    if "brand_names" in changes:
        changes["brand_names"] = ",".join(changes["brand_names"] or [])
    for k, v in changes.items():
        setattr(m, k, v)
    audit(db, "catalog.update", "medicine", m.id, actor=user, details={k: str(v) for k, v in changes.items()})
    db.commit()
    return {**medicine_dict(m), "is_active": m.is_active}


# ---------------------------------------------------------------- configuration & operations

@router.get("/api/admin/config")
def get_cfg(user: User = Depends(require("config.manage")), db: Session = Depends(get_db)):
    values = get_config(db)
    return [{"key": k, "value": values[k], "default": d.default, "description": d.description,
             "minimum": d.minimum, "maximum": d.maximum} for k, d in CONFIG_DEFS.items()]


@router.put("/api/admin/config")
def put_cfg(body: ConfigUpdateIn, user: User = Depends(require("config.manage")), db: Session = Depends(get_db)):
    try:
        for k, v in body.values.items():
            set_config(db, k, v, user.id)
    except KeyError as e:
        db.rollback()
        raise HTTPException(422, f"Unknown setting {e}") from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from e
    audit(db, "config.update", "system_config", None, actor=user, details=body.values)
    db.commit()
    return get_cfg(user, db)


@router.get("/api/admin/integrations")
def integrations(user: User = Depends(require("config.manage"))):
    s = get_settings()
    return {
        "demo_mode": s.demo_mode,
        "sms_mode": integration_mode(s),
        "africastalking": {
            "credentials_configured": s.at_configured,
            "username": s.at_username or None,
            "environment": s.at_environment,
            "sender_id_configured": bool(s.at_sender_id),
            "webhook_token_configured": bool(s.at_webhook_token),
            "ip_allowlist_configured": bool(s.at_webhook_allowed_ips),
            "ussd_service_code": s.at_ussd_service_code or None,
            "demo_sms_allowlist_count": len(s.demo_sms_allowlist_set),
        },
        "callbacks": {
            "ussd": "/api/webhooks/ussd?token=<AT_WEBHOOK_TOKEN>",
            "incoming_sms": "/api/webhooks/sms?token=<AT_WEBHOOK_TOKEN>",
            "delivery_reports": "/api/webhooks/delivery-report?token=<AT_WEBHOOK_TOKEN>",
        },
        "scheduler_enabled": s.scheduler_enabled,
    }


@router.post("/api/admin/jobs/run")
def run_jobs(user: User = Depends(require("config.manage")), db: Session = Depends(get_db)):
    checks = run_periodic_checks(db)
    sent = dispatch_due(db)
    audit(db, "jobs.run", "system", None, actor=user, details={**checks, "dispatched": sent})
    db.commit()
    return {**checks, "dispatched": sent}


@router.post("/api/admin/ripple/scan")
def ripple_scan(user: User = Depends(require("ripple.manage")), db: Session = Depends(get_db)):
    pairs = (db.query(InventoryItem.medicine_id, Facility.county_id).join(Facility)
             .filter(Facility.status == FacilityStatus.APPROVED).distinct().all())
    created = [a.id for m, c in pairs if (a := run_ripple(db, m, c))]
    audit(db, "ripple.scan", "system", None, actor=user, details={"pairs": len(pairs), "created": len(created)})
    db.commit()
    return {"evaluated": len(pairs), "created": created}


@router.post("/api/admin/demo/reset")
def demo_reset(user: User = Depends(require("demo.reset")), db: Session = Depends(get_db)):
    if not get_settings().demo_mode:
        raise HTTPException(403, "Demo reset is only available when DEMO_MODE=true")
    from app.seed import reset_demo

    summary = reset_demo(db, keep_user_id=user.id)
    audit(db, "demo.reset", "system", None, actor=user, details=summary)
    db.commit()
    return summary


@router.get("/api/manage/users")
def assignable_users(facility_id: str | None = None, user: User = Depends(require("alerts.manage")),
                     db: Session = Depends(get_db)):
    if facility_id:
        assert_facility_access(db, user, facility_id)
        rows = (db.query(User).join(FacilityMembership).filter(FacilityMembership.facility_id == facility_id,
                                                                 User.is_active.is_(True)).all())
    elif is_system_admin(user):
        rows = db.query(User).filter(User.role == UserRole.SYSTEM_ADMIN, User.is_active.is_(True)).all()
    else:
        rows = [user]
    return [{"id": u.id, "full_name": u.full_name, "role": u.role} for u in rows]
