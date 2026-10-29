from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import (
    County,
    Facility,
    FacilityMembership,
    FacilityStatus,
    FacilityType,
    InventoryItem,
    Location,
    Medicine,
    SearchRequest,
    StockReport,
    User,
    UserRole,
)
from app.ratelimit import client_ip, public_limit, sensitive_limit
from app.routers import PageQ, SizeQ, paginate
from app.schemas import FacilityRegisterIn, SmsSummaryIn
from app.security import hash_password
from app.services.audit import audit
from app.services.availability import (
    approved_facilities_query,
    availability_elsewhere,
    medicine_dict,
    medicine_query,
    public_facility_dict,
    search_availability,
    status_for_pairs,
)
from app.services.notifications import dispatch_in_background, queue_sms
from app.services.runtime_config import get_config
from app.services.sms_providers import integration_mode, provider_for

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/public/meta")
def meta(db: Session = Depends(get_db)):
    s = get_settings()
    cfg = get_config(db)
    return {
        "app_name": s.app_name,
        "demo_mode": s.demo_mode,
        "sms_mode": integration_mode(s),
        "fresh_hours": cfg["fresh_hours"],
        "unknown_after_days": cfg["unknown_after_days"],
        "ussd_service_code": s.at_ussd_service_code or None,
    }


@router.get("/medicines", dependencies=[Depends(public_limit("medicines"))])
def list_medicines(q: str | None = Query(None, max_length=60), page: int = PageQ, page_size: int = SizeQ,
                   long_term: bool | None = None, db: Session = Depends(get_db)):
    return paginate(medicine_query(db, q, long_term=long_term), page, page_size, medicine_dict)


@router.get("/medicines/{medicine_id}")
def get_medicine(medicine_id: str, db: Session = Depends(get_db)):
    m = db.get(Medicine, medicine_id)
    if not m or not m.is_active:
        raise HTTPException(404, "Medicine not found")
    return medicine_dict(m)


@router.get("/locations/counties")
def counties(db: Session = Depends(get_db)):
    counts = dict(
        db.query(Facility.county_id, func.count(Facility.id))
        .filter(Facility.status == FacilityStatus.APPROVED)
        .group_by(Facility.county_id)
        .all()
    )
    return [{"id": c.id, "code": c.code, "name": c.name, "participating_facilities": counts.get(c.id, 0)}
            for c in db.query(County).order_by(County.name)]


@router.get("/locations")
def locations(county_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Location)
    if county_id:
        q = q.filter(Location.county_id == county_id)
    return [{"id": l.id, "name": l.name, "county_id": l.county_id, "latitude": l.latitude,
             "longitude": l.longitude} for l in q.order_by(Location.name)]


@router.get("/facilities", dependencies=[Depends(public_limit("facilities"))])
def list_facilities(county_id: int | None = None, facility_type: FacilityType | None = None,
                    q: str | None = Query(None, max_length=60), page: int = PageQ, page_size: int = SizeQ,
                    db: Session = Depends(get_db)):
    query = approved_facilities_query(db)
    if county_id:
        query = query.filter(Facility.county_id == county_id)
    if facility_type:
        query = query.filter(Facility.facility_type == facility_type)
    if q:
        query = query.filter(func.lower(Facility.name).like(f"%{q.lower()}%"))
    return paginate(query.order_by(Facility.name), page, page_size, public_facility_dict)


@router.get("/facilities/{facility_id}")
def facility_detail(facility_id: str, db: Session = Depends(get_db)):
    f = approved_facilities_query(db).filter(Facility.id == facility_id).one_or_none()
    if not f:
        raise HTTPException(404, "Facility not found")
    med_ids = {i.medicine_id for i in db.query(InventoryItem.medicine_id).filter_by(facility_id=f.id)}
    med_ids |= {r.medicine_id for r in db.query(StockReport.medicine_id).filter_by(facility_id=f.id)}
    meds = db.query(Medicine).filter(Medicine.id.in_(med_ids), Medicine.is_active.is_(True)).all() if med_ids else []
    pairs = status_for_pairs(db, [f], meds)
    availability = []
    for m in sorted(meds, key=lambda m: m.generic_name):
        item, st, _ = pairs[(f.id, m.id)]
        show_qty = f.public_show_quantity and st.confirmed and st.status in ("available", "low")
        availability.append({
            "medicine": medicine_dict(m), "status": st.status, "status_label": st.label, "confirmed": st.confirmed,
            "last_updated_at": st.last_updated_at, "notes": st.notes,
            "quantity": st.quantity if show_qty else None, "unit": m.base_unit if show_qty else None,
        })
    return {**public_facility_dict(f), "availability": availability}


@router.post("/facilities/register", status_code=201, dependencies=[Depends(sensitive_limit("register"))])
def register_facility(body: FacilityRegisterIn, request: Request, db: Session = Depends(get_db)):
    if not db.get(County, body.county_id):
        raise HTTPException(422, "Unknown county")
    if body.location_id:
        loc = db.get(Location, body.location_id)
        if not loc or loc.county_id != body.county_id:
            raise HTTPException(422, "Location does not belong to the selected county")
    if db.query(User).filter(User.email == body.admin_email.lower()).first():
        raise HTTPException(409, "An account with this email already exists")
    next_num = (db.query(func.count(Facility.id)).scalar() or 0) + 1
    code = f"FAC-{next_num:04d}"
    while db.query(Facility).filter_by(code=code).first():
        next_num += 1
        code = f"FAC-{next_num:04d}"
    f = Facility(code=code, name=body.name.strip(), facility_type=body.facility_type, county_id=body.county_id,
                 location_id=body.location_id, address=body.address, phone=body.phone, email=body.email,
                 license_number=body.license_number, latitude=body.latitude, longitude=body.longitude,
                 status=FacilityStatus.PENDING)
    u = User(email=body.admin_email.lower(), full_name=body.admin_full_name, phone=body.admin_phone,
             password_hash=hash_password(body.admin_password), role=UserRole.FACILITY_ADMIN)
    db.add_all([f, u])
    db.flush()
    db.add(FacilityMembership(user_id=u.id, facility_id=f.id, role=UserRole.FACILITY_ADMIN, can_update_stock=True,
                              sms_phone=body.admin_phone))
    audit(db, "facility.register", "facility", f.id, actor=u, facility_id=f.id, ip=client_ip(request),
          details={"name": f.name, "county_id": f.county_id})
    db.commit()
    return {"id": f.id, "code": f.code, "status": f.status,
            "message": "Registration received. A system administrator must approve the facility before its "
                       "stock information is shown publicly. You can sign in and set up inventory now."}


def _county_name(db: Session, county_id: int | None) -> str | None:
    c = db.get(County, county_id) if county_id else None
    return c.name if c else None


@router.get("/availability/search", dependencies=[Depends(public_limit("search"))])
def availability_search(
    medicine_id: str | None = None,
    q: str | None = Query(None, min_length=2, max_length=60),
    county_id: int | None = None,
    location_id: int | None = None,
    facility_type: FacilityType | None = None,
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    radius_km: float | None = Query(None, gt=0, le=500),
    status: str | None = Query(None, pattern="^(available|low|out_of_stock|stale|unknown)$"),
    include_unknown: bool = True,
    db: Session = Depends(get_db),
):
    if medicine_id:
        m = db.get(Medicine, medicine_id)
        medicines = [m] if m and m.is_active else []
    elif q:
        medicines = medicine_query(db, q).limit(5).all()
    else:
        raise HTTPException(422, "Provide medicine_id or q")
    if not medicines:
        db.add(SearchRequest(query_text=(q or "")[:80] or None, county_id=county_id, channel="web"))
        db.commit()
        return {"medicines": [], "results": [], "alternatives": None,
                "notice": "No matching medicine in the catalog. Check the spelling or try the generic name."}
    results = search_availability(db, medicines, county_id=county_id, location_id=location_id,
                                  facility_type=facility_type, lat=lat, lng=lng, radius_km=radius_km,
                                  include_unknown=include_unknown, status_filter=status)
    available = [r for r in results if r["status"] in ("available", "low")]
    db.add(SearchRequest(medicine_id=medicines[0].id, query_text=(q or None), county_id=county_id, channel="web",
                         result_count=len(results), available_count=len(available)))
    db.commit()
    alternatives = None
    if not available and len(medicines) == 1:
        alternatives = {
            "other_areas": availability_elsewhere(db, medicines[0], county_id) if county_id else [],
            "can_subscribe": bool(county_id),
            "message": "No participating facility in this area has recently reported this medicine as available.",
        }
    return {
        "medicines": [medicine_dict(m) for m in medicines],
        "county": _county_name(db, county_id),
        "results": results,
        "alternatives": alternatives,
        "notice": "Availability is self-reported by participating facilities and may change at any time. "
                  "Nothing is reserved for you. Contact the facility before travelling. "
                  "Do not change prescribed medicines without a qualified health professional.",
    }


@router.post("/availability/sms-summary", status_code=202, dependencies=[Depends(sensitive_limit("sms_summary"))])
def sms_summary(body: SmsSummaryIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    m = db.get(Medicine, body.medicine_id)
    if not m:
        raise HTTPException(404, "Medicine not found")
    results = search_availability(db, [m], county_id=body.county_id, include_unknown=False)
    if body.facility_id:
        results = [r for r in results if r["facility"]["id"] == body.facility_id]
    top = [r for r in results if r["status"] in ("available", "low")][:3]
    is_demo = any(r["facility"]["is_demo"] for r in results)
    prefix = "StockOut Alert [DEMO]: " if is_demo else "StockOut Alert: "
    if top:
        parts = [f"{r['facility']['name']} ({r['status_label'].replace('Reported ', '')}, "
                 f"{r['last_updated_at'].strftime('%d %b %H:%M')}) Tel {r['facility']['phone'] or 'n/a'}" for r in top]
        msg = f"{prefix}{m.generic_name} {m.strength}: " + "; ".join(parts) + ". Stock may change. Call first."
    else:
        msg = f"{prefix}No recent available report for {m.generic_name} {m.strength} in this area."
    d = queue_sms(db, body.phone, msg, purpose="search_result", is_demo=is_demo)
    db.commit()
    background.add_task(dispatch_in_background)
    simulated = provider_for(get_settings(), body.phone).name == "simulated"
    return {"delivery_id": d.id if d else None, "status": "queued", "simulated": simulated, "preview": msg,
            "message": "SMS queued. " + ("This is a simulated SMS (demo mode). Nothing is sent to your phone."
                                         if simulated else
                                         "Sent via Africa's Talking; delivery is confirmed only by a delivery report.")}
