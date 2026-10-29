from app.models import (
    Alert,
    Facility,
    FacilityMembership,
    InventoryItem,
    NotificationDelivery,
    NotificationSubscription,
    StockMovement,
    StockReport,
    User,
)
from app.permissions import ROLE_PERMISSIONS
from app.services.availability import STATUS_LABELS, StatusResult, medicine_dict, raw_inventory_status
from app.utils import mask_phone


def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "phone": u.phone,
        "memberships": [
            {
                "facility_id": m.facility_id,
                "facility_name": m.facility.name,
                "facility_code": m.facility.code,
                "facility_status": m.facility.status,
                "role": m.role,
                "can_update_stock": m.can_update_stock,
            }
            for m in u.memberships
        ],
        "permissions": sorted(ROLE_PERMISSIONS.get(u.role, set())),
    }


def facility_private_dict(f: Facility) -> dict:
    return {
        "id": f.id,
        "code": f.code,
        "name": f.name,
        "facility_type": f.facility_type,
        "county": {"id": f.county.id, "name": f.county.name},
        "location": {"id": f.location.id, "name": f.location.name} if f.location else None,
        "address": f.address,
        "phone": f.phone,
        "email": f.email,
        "license_number": f.license_number,
        "latitude": f.latitude,
        "longitude": f.longitude,
        "status": f.status,
        "status_reason": f.status_reason,
        "public_show_quantity": f.public_show_quantity,
        "is_demo": f.is_demo,
        "created_at": f.created_at,
        "approved_at": f.approved_at,
    }


def membership_dict(m: FacilityMembership) -> dict:
    return {
        "id": m.id,
        "user_id": m.user_id,
        "full_name": m.user.full_name,
        "email": m.user.email,
        "phone": m.user.phone,
        "sms_phone": m.sms_phone,
        "role": m.role,
        "can_update_stock": m.can_update_stock,
        "receive_alerts": m.receive_alerts,
        "is_active": m.user.is_active,
        "created_at": m.created_at,
    }


def inventory_dict(i: InventoryItem, status: StatusResult | None = None, estimate=None) -> dict:
    raw = raw_inventory_status(i.quantity, i.min_threshold)
    d = {
        "id": i.id,
        "facility_id": i.facility_id,
        "facility_name": i.facility.name,
        "facility_code": i.facility.code,
        "medicine": medicine_dict(i.medicine),
        "quantity": i.quantity,
        "unit": i.unit,
        "min_threshold": i.min_threshold,
        "batch_number": i.batch_number,
        "expiry_date": i.expiry_date,
        "last_updated_at": i.last_updated_at,
        "last_updated_by": i.last_updated_by.full_name if i.last_updated_by else None,
        "verification_status": i.verification_status,
        "internal_notes": i.internal_notes,
        "version": i.version,
        "stock_status": raw,
        "public_status": status.status if status else None,
        "public_status_label": status.label if status else None,
    }
    if estimate is not None:
        d["estimate"] = {"days_remaining": estimate.days_remaining, "avg_daily": estimate.avg_daily,
                         "reason": estimate.reason}
    return d


def movement_dict(m: StockMovement) -> dict:
    return {
        "id": m.id,
        "inventory_id": m.inventory_id,
        "movement_type": m.movement_type,
        "quantity_delta": m.quantity_delta,
        "quantity_before": m.quantity_before,
        "quantity_after": m.quantity_after,
        "reason": m.reason,
        "source": m.source,
        "performed_by": m.performed_by.full_name if m.performed_by else None,
        "created_at": m.created_at,
        "medicine": m.inventory.medicine.display_name if m.inventory else None,
        "facility_name": m.inventory.facility.name if m.inventory else None,
    }


def report_dict(r: StockReport, private: bool = True) -> dict:
    d = {
        "id": r.id,
        "reference": r.reference,
        "facility": {"id": r.facility.id, "name": r.facility.name, "code": r.facility.code},
        "medicine": medicine_dict(r.medicine),
        "reported_status": r.reported_status,
        "reported_status_label": STATUS_LABELS.get(r.reported_status, r.reported_status),
        "source": r.source,
        "verification_status": r.verification_status,
        "created_at": r.created_at,
        "verified_at": r.verified_at,
    }
    if private:
        d["comment"] = r.comment
        d["history"] = [{"decision": v.decision, "note": v.note, "created_at": v.created_at} for v in r.verifications]
    return d


def alert_dict(a: Alert, with_evidence: bool = False) -> dict:
    d = {
        "id": a.id,
        "alert_type": a.alert_type,
        "severity": a.severity,
        "status": a.status,
        "title": a.title,
        "facility": {"id": a.facility.id, "name": a.facility.name, "is_demo": a.facility.is_demo}
        if a.facility else None,
        "medicine": medicine_dict(a.medicine) if a.medicine else None,
        "county": {"id": a.county.id, "name": a.county.name} if a.county else None,
        "evidence": a.evidence,
        "assigned_to": {"id": a.assigned_to.id, "full_name": a.assigned_to.full_name} if a.assigned_to else None,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "acknowledged_at": a.acknowledged_at,
        "resolved_at": a.resolved_at,
        "resolution_notes": a.resolution_notes,
        "escalation_level": a.escalation_level,
        "last_notified_at": a.last_notified_at,
    }
    if with_evidence:
        d["ripple_evidence"] = [
            {
                "facility_id": e.facility_id,
                "facility_name": e.facility.name,
                "source_type": e.source_type,
                "source_id": e.source_id,
                "observed_status": e.observed_status,
                "observed_at": e.observed_at,
                "verified": e.verified,
                "weight": e.weight,
                "counted": e.counted,
            }
            for e in sorted(a.ripple_evidence, key=lambda e: (not e.counted, -e.weight))
        ]
    return d


def delivery_dict(d: NotificationDelivery) -> dict:
    return {
        "id": d.id,
        "recipient": mask_phone(d.recipient),
        "message": d.message,
        "purpose": d.purpose,
        "status": d.status,
        "provider": d.provider,
        "provider_status": d.provider_status,
        "provider_message_id": d.provider_message_id,
        "failure_reason": d.failure_reason,
        "attempts": d.attempts,
        "is_demo": d.is_demo,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        "delivered_at": d.delivered_at,
    }


def subscription_dict(s: NotificationSubscription) -> dict:
    return {
        "id": s.id,
        "phone": mask_phone(s.phone),
        "medicine": medicine_dict(s.medicine),
        "county": {"id": s.county.id, "name": s.county.name},
        "is_active": s.is_active,
        "consent_at": s.consent_at,
        "unsubscribed_at": s.unsubscribed_at,
    }
