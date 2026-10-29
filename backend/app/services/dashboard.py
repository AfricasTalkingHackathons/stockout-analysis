"""Dashboard aggregates computed from persisted data only."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import utcnow
from app.models import (
    OPEN_ALERT_STATUSES,
    Alert,
    AlertType,
    Facility,
    FacilityStatus,
    InventoryItem,
    NotificationDelivery,
    SearchRequest,
    StockMovement,
    StockReport,
    VerificationStatus,
)
from app.serializers import alert_dict, movement_dict
from app.services.alerts import estimate_days_remaining
from app.services.availability import raw_inventory_status
from app.services.pickup import upcoming_demand
from app.services.runtime_config import get_config


def dashboard_status(item: InventoryItem, fresh_cutoff: datetime) -> str:
    if item.last_updated_at < fresh_cutoff:
        return "stale"
    return raw_inventory_status(item.quantity, item.min_threshold)


def overview(db: Session, facility_ids: list[str] | None, *, county_id=None, facility_id=None, medicine_id=None,
             status=None, severity=None, date_from=None, date_to=None, include_platform=False) -> dict:
    cfg = get_config(db)
    now = utcnow()
    fresh_cutoff = now - timedelta(hours=cfg["fresh_hours"])
    date_to = date_to or now
    date_from = date_from or (date_to - timedelta(days=30))

    fq = db.query(Facility).options(joinedload(Facility.county))
    if facility_ids is not None:
        fq = fq.filter(Facility.id.in_(facility_ids or ["-"]))
    if county_id:
        fq = fq.filter(Facility.county_id == county_id)
    if facility_id:
        fq = fq.filter(Facility.id == facility_id)
    facilities = fq.all()
    f_ids = [f.id for f in facilities]

    iq = db.query(InventoryItem).options(joinedload(InventoryItem.medicine), joinedload(InventoryItem.facility)) \
        .filter(InventoryItem.facility_id.in_(f_ids or ["-"]))
    if medicine_id:
        iq = iq.filter(InventoryItem.medicine_id == medicine_id)
    items = iq.all()
    statuses = {i.id: dashboard_status(i, fresh_cutoff) for i in items}
    counts = Counter(statuses.values())
    expiring_horizon = now.date() + timedelta(days=cfg["expiry_warning_days"])

    aq = db.query(Alert).filter(Alert.facility_id.in_(f_ids or ["-"]))
    ripple_q = db.query(Alert).filter(Alert.alert_type == AlertType.RIPPLE)
    if facility_ids is not None or county_id:
        counties = {f.county_id for f in facilities}
        ripple_q = ripple_q.filter(Alert.county_id.in_(counties or [-1]))
    if medicine_id:
        aq = aq.filter(Alert.medicine_id == medicine_id)
        ripple_q = ripple_q.filter(Alert.medicine_id == medicine_id)
    if severity:
        aq = aq.filter(Alert.severity == severity)
        ripple_q = ripple_q.filter(Alert.severity == severity)
    unresolved = aq.filter(Alert.status.in_(OPEN_ALERT_STATUSES)).count()
    ripple_open = ripple_q.filter(Alert.status.in_(OPEN_ALERT_STATUSES)).count()

    recent_alerts = (aq.union(ripple_q).filter(Alert.created_at >= date_from, Alert.created_at <= date_to)
                     .order_by(Alert.created_at.desc()).limit(10).all())
    mv = (db.query(StockMovement).join(InventoryItem)
          .options(joinedload(StockMovement.inventory).joinedload(InventoryItem.medicine),
                   joinedload(StockMovement.inventory).joinedload(InventoryItem.facility),
                   joinedload(StockMovement.performed_by))
          .filter(InventoryItem.facility_id.in_(f_ids or ["-"]), StockMovement.created_at >= date_from,
                  StockMovement.created_at <= date_to))
    if medicine_id:
        mv = mv.filter(InventoryItem.medicine_id == medicine_id)
    recent_movements = mv.order_by(StockMovement.created_at.desc()).limit(10).all()

    attention = []
    for i in items:
        st = statuses[i.id]
        expiring = i.expiry_date is not None and i.expiry_date <= expiring_horizon and i.quantity > 0
        if st in ("out_of_stock", "low", "stale") or expiring:
            if status and st != status:
                continue
            est = estimate_days_remaining(db, i, cfg, now)
            attention.append({
                "inventory_id": i.id, "facility_id": i.facility_id, "facility_name": i.facility.name,
                "medicine": i.medicine.display_name, "medicine_code": i.medicine.code, "quantity": i.quantity,
                "unit": i.unit, "min_threshold": i.min_threshold, "status": st,
                "expiry_date": i.expiry_date, "expiring": expiring, "last_updated_at": i.last_updated_at,
                "days_remaining": est.days_remaining, "estimate_note": None if est.days_remaining is not None
                else est.reason,
            })
    order = {"out_of_stock": 0, "low": 1, "stale": 2, "available": 3}
    attention.sort(key=lambda a: (order.get(a["status"], 4), a["days_remaining"] if a["days_remaining"] is not None
                                  else 1e9))

    trend_rows = (db.query(Alert.alert_type, Alert.created_at)
                  .filter(Alert.facility_id.in_(f_ids or ["-"]),
                          Alert.alert_type.in_([AlertType.STOCKOUT, AlertType.LOW_STOCK, AlertType.RIPPLE]),
                          Alert.created_at >= date_from, Alert.created_at <= date_to))
    if medicine_id:
        trend_rows = trend_rows.filter(Alert.medicine_id == medicine_id)
    by_day: dict[str, Counter] = defaultdict(Counter)
    for t, created in trend_rows.all():
        by_day[created.date().isoformat()][t] += 1
    for t, created in ripple_q.filter(Alert.created_at >= date_from, Alert.created_at <= date_to) \
            .with_entities(Alert.alert_type, Alert.created_at).all():
        by_day[created.date().isoformat()][t] += 1
    days = (date_to.date() - date_from.date()).days
    trend = []
    for k in range(days + 1):
        d = (date_from.date() + timedelta(days=k)).isoformat()
        c = by_day.get(d, Counter())
        trend.append({"date": d, "stockout": c[AlertType.STOCKOUT], "low_stock": c[AlertType.LOW_STOCK],
                      "ripple": c[AlertType.RIPPLE]})

    per_fac: dict[str, Counter] = defaultdict(Counter)
    for i in items:
        per_fac[i.facility_id][statuses[i.id]] += 1
    open_by_fac = dict(db.query(Alert.facility_id, func.count(Alert.id))
                       .filter(Alert.facility_id.in_(f_ids or ["-"]), Alert.status.in_(OPEN_ALERT_STATUSES))
                       .group_by(Alert.facility_id).all())
    comparison, map_points = [], []
    for f in facilities:
        c = per_fac.get(f.id, Counter())
        row = {"facility_id": f.id, "name": f.name, "code": f.code, "county": f.county.name, "status": f.status,
               "is_demo": f.is_demo, "items": sum(c.values()), "available": c["available"], "low": c["low"],
               "out_of_stock": c["out_of_stock"], "stale": c["stale"], "open_alerts": open_by_fac.get(f.id, 0)}
        comparison.append(row)
        if f.latitude is not None and f.longitude is not None:
            worst = "out_of_stock" if c["out_of_stock"] else "low" if c["low"] else "stale" if c["stale"] \
                else "available" if c["available"] else "unknown"
            map_points.append({**row, "latitude": f.latitude, "longitude": f.longitude, "worst_status": worst})

    out = {
        "generated_at": now,
        "filters": {"date_from": date_from, "date_to": date_to},
        "freshness": {"fresh_hours": cfg["fresh_hours"], "unknown_after_days": cfg["unknown_after_days"]},
        "totals": {
            "facilities": sum(1 for f in facilities if f.status == FacilityStatus.APPROVED),
            "medicine_records": len(items),
            "available": counts["available"],
            "low_stock": counts["low"],
            "out_of_stock": counts["out_of_stock"],
            "stale": counts["stale"],
            "unresolved_alerts": unresolved,
            "ripple_signals_open": ripple_open,
            "unverified_reports": db.query(StockReport).filter(
                StockReport.facility_id.in_(f_ids or ["-"]),
                StockReport.verification_status == VerificationStatus.UNVERIFIED).count(),
        },
        "recent_movements": [movement_dict(m) for m in recent_movements],
        "recent_alerts": [alert_dict(a) for a in recent_alerts],
        "attention": attention[:25],
        "trend": trend,
        "facility_comparison": comparison if (facility_ids is None or len(facilities) > 1) else [],
        "map": map_points,
        "has_demo_data": any(f.is_demo for f in facilities),
        "pickup_demand": upcoming_demand(db, f_ids, horizon_days=7),
    }
    if include_platform:
        out["platform"] = {
            "pending_facilities": db.query(Facility).filter_by(status=FacilityStatus.PENDING).count(),
            "suspended_facilities": db.query(Facility).filter_by(status=FacilityStatus.SUSPENDED).count(),
            "deliveries_by_status": dict(db.query(NotificationDelivery.status, func.count(NotificationDelivery.id))
                                         .group_by(NotificationDelivery.status).all()),
            "searches_last_7d": db.query(SearchRequest).filter(
                SearchRequest.created_at >= now - timedelta(days=7)).count(),
            "searches_by_channel_7d": dict(db.query(SearchRequest.channel, func.count(SearchRequest.id))
                                           .filter(SearchRequest.created_at >= now - timedelta(days=7))
                                           .group_by(SearchRequest.channel).all()),
        }
    return out
