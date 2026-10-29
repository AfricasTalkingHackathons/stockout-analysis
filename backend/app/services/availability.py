"""Public availability status calculation.

Status categories (see README "Availability categories"):
  available      - confirmed report, fresh, quantity above minimum threshold
  low            - confirmed report, fresh, quantity at/below threshold but above zero
  out_of_stock   - confirmed report, fresh, quantity zero (a real zero, not missing data)
  stale          - the newest confirmed report is older than fresh_hours, or the newest
                   signal is unconfirmed -> needs confirmation
  unknown        - no report at all, or the newest report is older than unknown_after_days
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import utcnow
from app.models import (
    County,
    Facility,
    FacilityStatus,
    InventoryItem,
    Location,
    Medicine,
    ReportedStatus,
    StockReport,
    VerificationStatus,
)
from app.services.runtime_config import get_config
from app.utils import haversine_km

STATUS_LABELS = {
    "available": "Reported available",
    "low": "Reported low stock",
    "out_of_stock": "Reported out of stock",
    "stale": "Stale report: needs confirmation",
    "unknown": "Unknown: no reliable recent report",
}
STATUS_RANK = {"available": 0, "low": 1, "stale": 2, "unknown": 3, "out_of_stock": 4}


def raw_inventory_status(quantity: int, min_threshold: int) -> str:
    if quantity <= 0:
        return ReportedStatus.OUT_OF_STOCK
    if quantity <= min_threshold:
        return ReportedStatus.LOW
    return ReportedStatus.AVAILABLE


@dataclass
class StatusResult:
    status: str
    confirmed: bool
    last_updated_at: datetime | None
    source: str | None
    raw_status: str | None = None
    quantity: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return STATUS_LABELS[self.status]


def compute_status(
    item: InventoryItem | None,
    reports: list[StockReport],
    cfg: dict[str, float],
    now: datetime | None = None,
) -> StatusResult:
    now = now or utcnow()
    fresh = timedelta(hours=cfg["fresh_hours"])
    unknown_after = timedelta(days=cfg["unknown_after_days"])

    signals: list[tuple[datetime, str, bool, str, int | None]] = []
    if item is not None:
        signals.append(
            (
                item.last_updated_at,
                raw_inventory_status(item.quantity, item.min_threshold),
                item.verification_status == VerificationStatus.VERIFIED,
                "facility_inventory",
                item.quantity,
            )
        )
    for r in reports:
        if r.verification_status == VerificationStatus.REJECTED:
            continue
        verified = r.verification_status == VerificationStatus.VERIFIED
        signals.append((r.created_at, r.reported_status, verified, f"{r.source}_report", None))

    if not signals:
        return StatusResult("unknown", False, None, None, notes=["No participating report for this medicine yet."])

    signals.sort(key=lambda s: s[0], reverse=True)
    newest_confirmed = next((s for s in signals if s[2]), None)
    newest = signals[0]
    notes: list[str] = []

    if not newest[2] and (newest_confirmed is None or newest[0] > newest_confirmed[0]):
        if now - newest[0] <= fresh:
            notes.append(
                f"A recent unverified report says '{STATUS_LABELS[newest[1]].replace('Reported ', '')}'. "
                "Awaiting facility confirmation."
            )

    if newest_confirmed is None:
        ts = newest[0]
        status = "unknown" if now - ts > unknown_after else "stale"
        return StatusResult(status, False, ts, newest[3], raw_status=newest[1], notes=notes)

    ts, raw, _, source, qty = newest_confirmed
    age = now - ts
    if age > unknown_after:
        return StatusResult("unknown", False, ts, source, raw_status=raw,
                            notes=notes + ["Last report is too old to be relied on."])
    if age > fresh:
        return StatusResult("stale", False, ts, source, raw_status=raw, quantity=qty,
                            notes=notes + ["This report may be out of date. Contact the facility to confirm."])
    return StatusResult(raw, True, ts, source, raw_status=raw, quantity=qty, notes=notes)


def medicine_query(db: Session, q: str | None, include_inactive: bool = False, long_term: bool | None = None):
    query = db.query(Medicine)
    if not include_inactive:
        query = query.filter(Medicine.is_active.is_(True))
    if long_term is True:
        query = query.filter(Medicine.is_long_term.is_(True))
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Medicine.generic_name).like(like),
                func.lower(Medicine.brand_names).like(like),
                func.lower(Medicine.code).like(like),
            )
        )
    return query.order_by(Medicine.generic_name, Medicine.strength)


def public_facility_dict(f: Facility) -> dict:
    return {
        "id": f.id,
        "code": f.code,
        "name": f.name,
        "facility_type": f.facility_type,
        "county": {"id": f.county.id, "name": f.county.name} if f.county else None,
        "town": f.location.name if f.location else None,
        "address": f.address,
        "phone": f.phone,
        "latitude": f.latitude,
        "longitude": f.longitude,
        "is_demo": f.is_demo,
    }


def medicine_dict(m: Medicine) -> dict:
    return {
        "id": m.id,
        "code": m.code,
        "generic_name": m.generic_name,
        "brand_names": [b.strip() for b in m.brand_names.split(",") if b.strip()],
        "strength": m.strength,
        "dosage_form": m.dosage_form,
        "base_unit": m.base_unit,
        "display_name": m.display_name,
        "requires_prescription": m.requires_prescription,
        "category": m.category,
        "is_long_term": m.is_long_term,
    }


def _recent_reports(db: Session, facility_ids: list[str], medicine_ids: list[str], since: datetime):
    if not facility_ids or not medicine_ids:
        return {}
    out: dict[tuple[str, str], list[StockReport]] = {}
    rows = (
        db.query(StockReport)
        .filter(
            StockReport.facility_id.in_(facility_ids),
            StockReport.medicine_id.in_(medicine_ids),
            StockReport.created_at >= since,
        )
        .all()
    )
    for r in rows:
        out.setdefault((r.facility_id, r.medicine_id), []).append(r)
    return out


def status_for_pairs(db: Session, facilities: list[Facility], medicines: list[Medicine], cfg=None, now=None):
    """Return {(facility_id, medicine_id): (inventory_item|None, StatusResult)}."""
    cfg = cfg or get_config(db)
    now = now or utcnow()
    f_ids = [f.id for f in facilities]
    m_ids = [m.id for m in medicines]
    items = {}
    if f_ids and m_ids:
        for it in db.query(InventoryItem).filter(
            InventoryItem.facility_id.in_(f_ids), InventoryItem.medicine_id.in_(m_ids)
        ):
            items[(it.facility_id, it.medicine_id)] = it
    reports = _recent_reports(db, f_ids, m_ids, now - timedelta(days=cfg["unknown_after_days"]))
    out = {}
    for f in facilities:
        for m in medicines:
            key = (f.id, m.id)
            item = items.get(key)
            reps = reports.get(key, [])
            out[key] = (item, compute_status(item, reps, cfg, now), bool(item or reps))
    return out


def approved_facilities_query(db: Session):
    return (
        db.query(Facility)
        .options(joinedload(Facility.county), joinedload(Facility.location))
        .filter(Facility.status == FacilityStatus.APPROVED)
    )


def search_availability(
    db: Session,
    medicines: list[Medicine],
    county_id: int | None = None,
    location_id: int | None = None,
    facility_type: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    include_unknown: bool = True,
    status_filter: str | None = None,
) -> list[dict]:
    q = approved_facilities_query(db)
    if county_id:
        q = q.filter(Facility.county_id == county_id)
    if location_id:
        q = q.filter(Facility.location_id == location_id)
    if facility_type:
        q = q.filter(Facility.facility_type == facility_type)
    facilities = q.all()
    cfg = get_config(db)
    now = utcnow()
    pairs = status_for_pairs(db, facilities, medicines, cfg, now)
    show_unknown_rows = include_unknown and len(medicines) == 1
    results = []
    for f in facilities:
        distance = None
        if lat is not None and lng is not None and f.latitude is not None and f.longitude is not None:
            distance = round(haversine_km(lat, lng, f.latitude, f.longitude), 2)
            if radius_km and distance > radius_km:
                continue
        for m in medicines:
            item, st, has_data = pairs[(f.id, m.id)]
            if not has_data and not show_unknown_rows:
                continue
            if status_filter and st.status != status_filter:
                continue
            show_qty = (
                f.public_show_quantity and st.confirmed and st.quantity is not None
                and st.status in ("available", "low")
            )
            results.append(
                {
                    "facility": public_facility_dict(f),
                    "medicine": medicine_dict(m),
                    "status": st.status,
                    "status_label": st.label,
                    "confirmed": st.confirmed,
                    "last_updated_at": st.last_updated_at,
                    "age_hours": round((now - st.last_updated_at).total_seconds() / 3600, 1)
                    if st.last_updated_at else None,
                    "source": st.source,
                    "quantity": st.quantity if show_qty else None,
                    "unit": m.base_unit if show_qty else None,
                    "distance_km": distance,
                    "notes": st.notes,
                }
            )

    def sort_key(r):
        dist = r["distance_km"] if r["distance_km"] is not None else float("inf")
        age = r["age_hours"] if r["age_hours"] is not None else float("inf")
        return (STATUS_RANK[r["status"]] >= 3, dist, STATUS_RANK[r["status"]], age)

    results.sort(key=sort_key)
    return results


def availability_elsewhere(db: Session, medicine: Medicine, exclude_county_id: int | None) -> list[dict]:
    """Counties (other than the searched one) with confirmed availability — for 'expand search area'."""
    q = approved_facilities_query(db)
    if exclude_county_id:
        q = q.filter(Facility.county_id != exclude_county_id)
    facilities = q.all()
    pairs = status_for_pairs(db, facilities, [medicine])
    counts: dict[int, dict] = {}
    for f in facilities:
        _, st, _ = pairs[(f.id, medicine.id)]
        if st.status in ("available", "low"):
            c = counts.setdefault(f.county_id, {"county_id": f.county_id, "county": f.county.name, "facilities": 0})
            c["facilities"] += 1
    return sorted(counts.values(), key=lambda c: -c["facilities"])


def county_and_location(db: Session, county_id: int | None, location_id: int | None):
    county = db.get(County, county_id) if county_id else None
    location = db.get(Location, location_id) if location_id else None
    return county, location
