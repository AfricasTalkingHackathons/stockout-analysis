from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db, utcnow
from app.deps import accessible_facility_ids, is_system_admin, require
from app.models import (
    OPEN_ALERT_STATUSES,
    Alert,
    AlertStatus,
    AlertType,
    Facility,
    FacilityMembership,
    User,
)
from app.permissions import has_permission
from app.routers import PageQ, SizeQ, paginate
from app.schemas import AlertActionIn, AlertAssignIn, AlertResolveIn
from app.serializers import alert_dict
from app.services.audit import audit

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _visible(db: Session, user: User):
    q = db.query(Alert).options(joinedload(Alert.facility), joinedload(Alert.medicine), joinedload(Alert.county),
                                joinedload(Alert.assigned_to))
    ids = accessible_facility_ids(db, user)
    if ids is None:
        return q
    # Facility users see their facilities' alerts and ripple signals in counties where they operate.
    county_ids = [c for (c,) in db.query(Facility.county_id).filter(Facility.id.in_(ids or ["-"]))]
    return q.filter(or_(Alert.facility_id.in_(ids or ["-"]),
                        (Alert.alert_type == AlertType.RIPPLE) & Alert.county_id.in_(county_ids or [-1])))


@router.get("")
def list_alerts(status: str | None = Query(None, pattern="^(open|acknowledged|investigating|resolved|dismissed|active)$"),
                alert_type: str | None = None, severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
                facility_id: str | None = None, medicine_id: str | None = None, county_id: int | None = None,
                date_from: datetime | None = None, date_to: datetime | None = None,
                page: int = PageQ, page_size: int = SizeQ,
                user: User = Depends(require("alerts.view")), db: Session = Depends(get_db)):
    q = _visible(db, user)
    if status == "active":
        q = q.filter(Alert.status.in_(OPEN_ALERT_STATUSES))
    elif status:
        q = q.filter(Alert.status == status)
    for col, val in ((Alert.alert_type, alert_type), (Alert.severity, severity), (Alert.facility_id, facility_id),
                     (Alert.medicine_id, medicine_id), (Alert.county_id, county_id)):
        if val:
            q = q.filter(col == val)
    if date_from:
        q = q.filter(Alert.created_at >= date_from)
    if date_to:
        q = q.filter(Alert.created_at <= date_to)
    return paginate(q.order_by(Alert.created_at.desc()), page, page_size, alert_dict)


def _get(db: Session, user: User, alert_id: str) -> Alert:
    a = _visible(db, user).filter(Alert.id == alert_id).one_or_none()
    if not a:
        raise HTTPException(404, "Alert not found")
    return a


def _can_manage(user: User, a: Alert) -> None:
    if a.alert_type == AlertType.RIPPLE and not has_permission(user.role, "ripple.manage"):
        if a.status != AlertStatus.OPEN:
            raise HTTPException(403, "Only administrators can change a ripple signal")


@router.get("/{alert_id}")
def get_alert(alert_id: str, user: User = Depends(require("alerts.view")), db: Session = Depends(get_db)):
    return alert_dict(_get(db, user, alert_id), with_evidence=True)


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: str, body: AlertActionIn | None = None, user: User = Depends(require("alerts.manage")),
                db: Session = Depends(get_db)):
    a = _get(db, user, alert_id)
    _can_manage(user, a)
    if a.status not in (AlertStatus.OPEN,):
        raise HTTPException(409, f"Alert is already {a.status}")
    a.status, a.acknowledged_at, a.acknowledged_by_id = AlertStatus.ACKNOWLEDGED, utcnow(), user.id
    if a.assigned_to_id is None:
        a.assigned_to = user
    audit(db, "alert.acknowledge", "alert", a.id, actor=user, facility_id=a.facility_id,
          details={"note": body.note if body else None})
    db.commit()
    return alert_dict(a)


@router.post("/{alert_id}/investigate")
def investigate(alert_id: str, body: AlertActionIn | None = None, user: User = Depends(require("alerts.manage")),
                db: Session = Depends(get_db)):
    a = _get(db, user, alert_id)
    if a.alert_type == AlertType.RIPPLE and not has_permission(user.role, "ripple.manage"):
        raise HTTPException(403, "Only administrators can open a ripple investigation")
    if a.status not in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED):
        raise HTTPException(409, f"Alert is already {a.status}")
    a.status = AlertStatus.INVESTIGATING
    a.acknowledged_at = a.acknowledged_at or utcnow()
    a.acknowledged_by_id = a.acknowledged_by_id or user.id
    a.assigned_to = a.assigned_to or user
    audit(db, "alert.investigate", "alert", a.id, actor=user, facility_id=a.facility_id,
          details={"note": body.note if body else None})
    db.commit()
    return alert_dict(a)


@router.post("/{alert_id}/resolve")
def resolve(alert_id: str, body: AlertResolveIn, user: User = Depends(require("alerts.manage")),
            db: Session = Depends(get_db)):
    a = _get(db, user, alert_id)
    if a.alert_type == AlertType.RIPPLE and not has_permission(user.role, "ripple.manage"):
        raise HTTPException(403, "Only administrators can resolve a ripple signal")
    if a.status in (AlertStatus.RESOLVED, AlertStatus.DISMISSED):
        raise HTTPException(409, f"Alert is already {a.status}")
    a.status = AlertStatus.RESOLVED if body.outcome == "resolved" else AlertStatus.DISMISSED
    a.resolved_at, a.resolved_by_id, a.resolution_notes = utcnow(), user.id, body.resolution_notes
    audit(db, f"alert.{body.outcome}", "alert", a.id, actor=user, facility_id=a.facility_id,
          details={"notes": body.resolution_notes})
    db.commit()
    return alert_dict(a)


@router.post("/{alert_id}/assign")
def assign(alert_id: str, body: AlertAssignIn, user: User = Depends(require("alerts.manage")),
           db: Session = Depends(get_db)):
    a = _get(db, user, alert_id)
    if body.user_id:
        target = db.get(User, body.user_id)
        if not target or not target.is_active:
            raise HTTPException(404, "User not found")
        if a.facility_id and not is_system_admin(target):
            if not db.query(FacilityMembership).filter_by(user_id=target.id, facility_id=a.facility_id).first():
                raise HTTPException(422, "User is not a member of this facility")
    a.assigned_to = db.get(User, body.user_id) if body.user_id else None
    audit(db, "alert.assign", "alert", a.id, actor=user, facility_id=a.facility_id, details={"to": body.user_id})
    db.commit()
    return alert_dict(a)
