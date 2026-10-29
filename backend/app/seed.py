"""Reference data + fictional demo scenario.

Usage:
  python -m app.seed reference            # counties, towns, roles, medicine catalog (idempotent)
  python -m app.seed demo                 # reference + fictional demo scenario
  python -m app.seed reset-demo           # remove ONLY demo records and recreate the scenario
  python -m app.seed create-admin EMAIL "Full Name"   # password from ADMIN_PASSWORD or prompt

All demo facilities are fictional, flagged is_demo=True and named "(Demo)". They are not real
facilities, and their stock levels are synthetic.
"""

import getpass
import os
import sys
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import (
    Alert,
    AlertType,
    County,
    Facility,
    FacilityMembership,
    FacilityStatus,
    InboundMessage,
    InventoryItem,
    Location,
    Medicine,
    PickupSchedule,
    MovementType,
    NotificationDelivery,
    RippleEvidence,
    Role,
    RolePermission,
    StockMovement,
    StockReport,
    StockReportVerification,
    User,
    UserRole,
    UssdSession,
)
from app.permissions import ROLE_DESCRIPTIONS, ROLE_PERMISSIONS
from app.security import hash_password
from app.services.inventory import create_inventory

COUNTIES = [
    "Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita-Taveta", "Garissa", "Wajir", "Mandera", "Marsabit",
    "Isiolo", "Meru", "Tharaka-Nithi", "Embu", "Kitui", "Machakos", "Makueni", "Nyandarua", "Nyeri", "Kirinyaga",
    "Murang'a", "Kiambu", "Turkana", "West Pokot", "Samburu", "Trans Nzoia", "Uasin Gishu", "Elgeyo-Marakwet",
    "Nandi", "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado", "Kericho", "Bomet", "Kakamega", "Vihiga",
    "Bungoma", "Busia", "Siaya", "Kisumu", "Homa Bay", "Migori", "Kisii", "Nyamira", "Nairobi",
]

# Approximate town-centre coordinates (public geographic knowledge).
LOCATIONS = {
    "Nairobi": [("Westlands", -1.2676, 36.8108), ("Kilimani", -1.2921, 36.7856), ("Embakasi", -1.3197, 36.8947),
                ("Kasarani", -1.2216, 36.8969), ("Nairobi CBD", -1.2864, 36.8172), ("Kibera", -1.3133, 36.7876)],
    "Kiambu": [("Thika", -1.0388, 37.0834), ("Ruiru", -1.1466, 36.9609), ("Kikuyu", -1.2463, 36.6629),
               ("Kiambu Town", -1.1714, 36.8356)],
    "Mombasa": [("Mombasa Island", -4.0435, 39.6682), ("Nyali", -4.0225, 39.7139), ("Likoni", -4.0833, 39.6667)],
    "Kisumu": [("Kisumu Central", -0.0917, 34.7680), ("Kondele", -0.0868, 34.7750)],
    "Nakuru": [("Nakuru Town", -0.3031, 36.0800), ("Naivasha", -0.7167, 36.4333)],
    "Uasin Gishu": [("Eldoret", 0.5143, 35.2698)],
    "Machakos": [("Machakos Town", -1.5177, 37.2634), ("Athi River", -1.4560, 36.9780)],
    "Kajiado": [("Kitengela", -1.4746, 36.9606), ("Ngong", -1.3524, 36.6600)],
    "Meru": [("Meru Town", 0.0470, 37.6490)],
    "Kakamega": [("Kakamega Town", 0.2827, 34.7519)],
    "Nyeri": [("Nyeri Town", -0.4201, 36.9476)],
    "Garissa": [("Garissa Town", -0.4532, 39.6461)],
    "Turkana": [("Lodwar", 3.1191, 35.5973)],
    "Kilifi": [("Malindi", -3.2192, 40.1169), ("Kilifi Town", -3.6305, 39.8499)],
}

# Generic names follow the Kenya Essential Medicines List style. Brand names are search aliases only.
# Last flag: is_long_term — typically collected on a repeating schedule. Not a diagnosis.
MEDICINES = [
    ("MED001", "Amoxicillin", "Amoxil", "500 mg", "capsule", "capsule", "Antibiotic", True, False),
    ("MED002", "Paracetamol", "Panadol,Calpol", "500 mg", "tablet", "tablet", "Analgesic", False, False),
    ("MED003", "Metformin", "Glucophage", "500 mg", "tablet", "tablet", "Antidiabetic", True, True),
    ("MED004", "Amlodipine", "Norvasc", "5 mg", "tablet", "tablet", "Antihypertensive", True, True),
    ("MED005", "Artemether + Lumefantrine", "Coartem,AL", "20 mg/120 mg", "tablet", "tablet", "Antimalarial", True, False),
    ("MED006", "Oral Rehydration Salts", "ORS", "20.5 g/L", "sachet", "sachet", "Rehydration", False, False),
    ("MED007", "Zinc sulfate", "", "20 mg", "dispersible tablet", "tablet", "Supplement", False, False),
    ("MED008", "Salbutamol", "Ventolin", "100 mcg/dose", "inhaler", "inhaler", "Respiratory", True, True),
    ("MED009", "Insulin soluble human", "Actrapid", "100 IU/mL 10 mL", "injection", "vial", "Antidiabetic", True, True),
    ("MED010", "Ferrous sulfate + Folic acid", "", "200 mg/0.4 mg", "tablet", "tablet", "Supplement", False, True),
    ("MED011", "Cotrimoxazole", "Septrin", "960 mg", "tablet", "tablet", "Antibiotic", True, False),
    ("MED012", "Losartan", "Cozaar", "50 mg", "tablet", "tablet", "Antihypertensive", True, True),
    ("MED013", "Ibuprofen", "Brufen", "400 mg", "tablet", "tablet", "Analgesic", False, False),
    ("MED014", "Omeprazole", "Losec", "20 mg", "capsule", "capsule", "Gastrointestinal", True, False),
    ("MED015", "Medroxyprogesterone acetate", "Depo-Provera", "150 mg/mL", "injection", "vial",
     "Family planning", True, True),
    ("MED016", "Tenofovir + Lamivudine + Dolutegravir", "TLD", "300/300/50 mg", "tablet", "tablet",
     "Antiretroviral", True, True),
    ("MED017", "Hydrochlorothiazide", "", "25 mg", "tablet", "tablet", "Antihypertensive", True, True),
    ("MED018", "Ceftriaxone", "Rocephin", "1 g", "powder for injection", "vial", "Antibiotic", True, False),
    ("MED019", "Rifampicin + Isoniazid + Pyrazinamide + Ethambutol", "RHZE", "150/75/400/275 mg",
     "tablet", "tablet", "Antitubercular", True, True),
    ("MED020", "Rifampicin + Isoniazid", "RH", "150/75 mg", "tablet", "tablet", "Antitubercular", True, True),
    ("MED021", "Isoniazid", "", "300 mg", "tablet", "tablet", "Antitubercular", True, True),
]

DEMO_EMAIL_DOMAIN = "demo.stockout.example"


def seed_reference(db: Session) -> None:
    for role, desc in ROLE_DESCRIPTIONS.items():
        if not db.get(Role, role.value):
            db.add(Role(name=role.value, description=desc))
    db.flush()
    db.execute(delete(RolePermission))
    for role, perms in ROLE_PERMISSIONS.items():
        for p in sorted(perms):
            db.add(RolePermission(role_name=str(role), permission=p))
    for i, name in enumerate(COUNTIES, start=1):
        if not db.query(County).filter_by(name=name).first():
            db.add(County(code=f"{i:03d}", name=name))
    db.flush()
    for county_name, towns in LOCATIONS.items():
        c = db.query(County).filter_by(name=county_name).one()
        for town, lat, lng in towns:
            if not db.query(Location).filter_by(county_id=c.id, name=town).first():
                db.add(Location(county_id=c.id, name=town, latitude=lat, longitude=lng))
    for code, gen, brands, strength, form, unit, cat, rx, long_term in MEDICINES:
        row = db.query(Medicine).filter_by(code=code).first()
        if row is None:
            db.add(Medicine(code=code, generic_name=gen, brand_names=brands, strength=strength, dosage_form=form,
                            base_unit=unit, category=cat, requires_prescription=rx, is_long_term=long_term))
        else:
            row.is_long_term = long_term
            row.category = cat
    db.commit()


def _user(db: Session, email: str, name: str, role: str, phone: str | None) -> User:
    u = db.query(User).filter_by(email=email).one_or_none()
    pw = hash_password(get_settings().demo_password)
    if u is None:
        u = User(email=email, full_name=name, role=role, phone=phone, password_hash=pw, is_demo=True)
        db.add(u)
        db.flush()
    else:
        u.full_name, u.role, u.phone, u.password_hash, u.is_active = name, role, phone, pw, True
    return u


def _loc(db: Session, county: str, town: str) -> tuple[County, Location]:
    c = db.query(County).filter_by(name=county).one()
    return c, db.query(Location).filter_by(county_id=c.id, name=town).one()


DEMO_FACILITIES = [
    # code, name, type, county, town, lat, lng, status, show_qty
    ("FAC-D001", "Mwangaza Community Pharmacy (Demo)", "pharmacy", "Nairobi", "Westlands", -1.2649, 36.8031,
     "approved", True),
    ("FAC-D002", "Tumaini Health Centre (Demo)", "health_centre", "Nairobi", "Kilimani", -1.2897, 36.7869,
     "approved", False),
    ("FAC-D003", "Baraka Medical Clinic (Demo)", "clinic", "Nairobi", "Westlands", -1.2712, 36.8125,
     "approved", True),
    ("FAC-D004", "Upendo Chemist (Demo)", "pharmacy", "Nairobi", "Kilimani", -1.2950, 36.7820, "approved", True),
    ("FAC-D005", "Jamii Dispensary (Demo)", "dispensary", "Kiambu", "Ruiru", -1.1450, 36.9580, "approved", True),
    ("FAC-D006", "Neema Pharmacy (Demo)", "pharmacy", "Nairobi", "Embakasi", -1.3180, 36.8920, "pending", False),
]

# facility code -> [(medicine code, quantity, min threshold)]
DEMO_STOCK = {
    "FAC-D001": [("MED001", 400, 100), ("MED002", 2500, 500), ("MED003", 900, 300), ("MED005", 240, 72),
                 ("MED006", 150, 40), ("MED008", 12, 5), ("MED016", 240, 80), ("MED019", 120, 40)],
    "FAC-D002": [("MED001", 60, 100), ("MED002", 1800, 500), ("MED005", 30, 72), ("MED006", 300, 60),
                 ("MED010", 1200, 300), ("MED015", 40, 10), ("MED016", 18, 80), ("MED019", 0, 40)],
    "FAC-D003": [("MED001", 250, 80), ("MED002", 900, 300), ("MED004", 600, 150), ("MED013", 700, 200),
                 ("MED016", 400, 80), ("MED019", 600, 40)],
    "FAC-D004": [("MED001", 300, 50), ("MED002", 1000, 200), ("MED003", 500, 100)],
    "FAC-D005": [("MED001", 500, 100), ("MED002", 1500, 300), ("MED005", 180, 72), ("MED006", 200, 50),
                 ("MED016", 200, 80), ("MED019", 180, 40)],
}

DEMO_STAFF = [
    # email local part, name, role, facility code, sms phone
    ("pharmacist.mwangaza", "Demo Pharmacist (Mwangaza)", UserRole.FACILITY_ADMIN, "FAC-D001", "+254700000011"),
    ("staff.mwangaza", "Demo Stock Clerk (Mwangaza)", UserRole.FACILITY_STAFF, "FAC-D001", "+254700000012"),
    ("admin.tumaini", "Demo Facility Admin (Tumaini)", UserRole.FACILITY_ADMIN, "FAC-D002", "+254700000021"),
    ("admin.baraka", "Demo Facility Admin (Baraka)", UserRole.FACILITY_ADMIN, "FAC-D003", "+254700000031"),
    ("admin.upendo", "Demo Facility Admin (Upendo)", UserRole.FACILITY_ADMIN, "FAC-D004", "+254700000041"),
    ("admin.jamii", "Demo Facility Admin (Jamii)", UserRole.FACILITY_ADMIN, "FAC-D005", "+254700000051"),
    ("admin.neema", "Demo Facility Admin (Neema)", UserRole.FACILITY_ADMIN, "FAC-D006", "+254700000061"),
]


def _backfill_history(db: Session, item: InventoryItem, days: int, daily: int) -> None:
    """Rewrite the item's history as `days` of daily dispensing ending at the current quantity."""
    now = utcnow()
    final = item.quantity
    start = final + days * daily
    db.query(StockMovement).filter_by(inventory_id=item.id).delete()
    t0 = now - timedelta(days=days, hours=2)
    db.add(StockMovement(inventory_id=item.id, movement_type=MovementType.INITIAL, quantity_delta=start,
                         quantity_before=0, quantity_after=start, reason="Initial stock record (demo)",
                         source="demo", created_at=t0))
    q = start
    for d in range(days):
        db.add(StockMovement(inventory_id=item.id, movement_type=MovementType.DISPENSE, quantity_delta=-daily,
                             quantity_before=q, quantity_after=q - daily, reason="Daily dispensing (demo)",
                             source="demo", created_at=t0 + timedelta(days=d + 1)))
        q -= daily


def seed_demo(db: Session) -> dict:
    seed_reference(db)
    s = get_settings()
    staff_phone = s.demo_staff_phone or None
    _user(db, f"admin@{DEMO_EMAIL_DOMAIN}", "Demo System Administrator", UserRole.SYSTEM_ADMIN,
          staff_phone or "+254700000001")
    facilities = {}
    for code, name, ftype, county, town, lat, lng, status, show in DEMO_FACILITIES:
        c, loc = _loc(db, county, town)
        f = Facility(code=code, name=name, facility_type=ftype, county_id=c.id, location_id=loc.id,
                     address=f"Fictional demo address, {town}", phone=None, latitude=lat, longitude=lng,
                     status=status, public_show_quantity=show, is_demo=True,
                     approved_at=utcnow() if status == "approved" else None)
        db.add(f)
        facilities[code] = f
    db.flush()
    for local, name, role, fcode, phone in DEMO_STAFF:
        if staff_phone and local == "pharmacist.mwangaza":
            phone = staff_phone
        u = _user(db, f"{local}@{DEMO_EMAIL_DOMAIN}", name, role, phone)
        db.add(FacilityMembership(user_id=u.id, facility_id=facilities[fcode].id, role=role, can_update_stock=True,
                                  sms_phone=phone))
    db.flush()

    meds = {m.code: m for m in db.query(Medicine)}
    admin = db.query(User).filter_by(email=f"admin@{DEMO_EMAIL_DOMAIN}").one()
    items = {}
    for fcode, rows in DEMO_STOCK.items():
        for mcode, qty, minimum in rows:
            out = create_inventory(db, facilities[fcode], meds[mcode], qty, minimum, admin, source="demo",
                                   internal_notes="Synthetic demo stock")
            items[(fcode, mcode)] = out.item
    db.flush()

    # Consumption history so days-remaining estimates are meaningful for some items.
    _backfill_history(db, items[("FAC-D001", "MED001")], 21, 25)
    _backfill_history(db, items[("FAC-D002", "MED001")], 14, 12)
    _backfill_history(db, items[("FAC-D001", "MED003")], 14, 30)

    # Upendo's records are 10 days old -> shown as "stale" publicly.
    old = utcnow() - timedelta(days=10)
    for (fcode, _), it in items.items():
        if fcode == "FAC-D004":
            it.last_updated_at = old
            db.query(StockMovement).filter_by(inventory_id=it.id).update({"created_at": old})
    # An expiring batch for the expiry warning.
    items[("FAC-D003", "MED004")].batch_number = "DEMO-B17"
    items[("FAC-D003", "MED004")].expiry_date = (utcnow() + timedelta(days=25)).date()

    # Alerts raised by create_inventory reflect the seeded state; backdate them to look realistic.
    for a in db.query(Alert).filter(Alert.facility_id.in_([f.id for f in facilities.values()])):
        a.created_at = utcnow() - timedelta(hours=3)
    # Seeded alerts should not trigger SMS on reset.
    db.query(NotificationDelivery).filter(NotificationDelivery.is_demo.is_(True),
                                          NotificationDelivery.status == "queued").delete()

    # Fictional patient reminder: usual clinic is low on TLD so the refill finder shows alternatives.
    from app.services.pickup import today_ke, upsert_schedule
    upsert_schedule(
        db, phone="+254700000088", medicine=meds["MED016"], county_id=facilities["FAC-D002"].county_id,
        next_pickup_on=today_ke() + timedelta(days=2), interval_days=30, remind_days_before=3,
        preferred_facility=facilities["FAC-D002"], consent_source="demo", is_demo=True,
    )
    db.commit()
    return {"facilities": len(facilities), "inventory_items": len(items), "users": len(DEMO_STAFF) + 1}


def clear_demo(db: Session) -> dict:
    ids = [f for (f,) in db.query(Facility.id).filter(Facility.is_demo.is_(True))]
    ripple_ids = []
    for a in db.query(Alert).filter(Alert.alert_type == AlertType.RIPPLE):
        facs = {e.facility_id for e in a.ripple_evidence}
        if (facs and facs <= set(ids)) or (not facs and a.evidence.get("is_demo")):
            ripple_ids.append(a.id)
    inv_ids = select(InventoryItem.id).where(InventoryItem.facility_id.in_(ids))
    report_ids = select(StockReport.id).where(StockReport.facility_id.in_(ids))
    db.execute(delete(RippleEvidence).where(RippleEvidence.facility_id.in_(ids)))
    db.execute(delete(RippleEvidence).where(RippleEvidence.alert_id.in_(ripple_ids)))
    db.execute(delete(NotificationDelivery).where(
        NotificationDelivery.facility_id.in_(ids) | NotificationDelivery.is_demo.is_(True)
        | NotificationDelivery.alert_id.in_(ripple_ids)))
    db.execute(delete(Alert).where(Alert.facility_id.in_(ids) | Alert.id.in_(ripple_ids)))
    db.execute(delete(StockReportVerification).where(StockReportVerification.report_id.in_(report_ids)))
    db.execute(delete(StockReport).where(StockReport.facility_id.in_(ids)))
    db.execute(delete(StockMovement).where(StockMovement.inventory_id.in_(inv_ids)))
    db.execute(delete(InventoryItem).where(InventoryItem.facility_id.in_(ids)))
    db.execute(delete(FacilityMembership).where(FacilityMembership.facility_id.in_(ids)))
    db.execute(delete(Facility).where(Facility.id.in_(ids)))
    db.execute(delete(PickupSchedule).where(PickupSchedule.is_demo.is_(True)))
    db.execute(delete(UssdSession).where(UssdSession.is_simulated.is_(True)))
    db.execute(delete(InboundMessage).where(InboundMessage.provider_message_id.like("SIM-%")))
    db.commit()
    return {"removed_facilities": len(ids), "removed_ripple_alerts": len(ripple_ids)}


def reset_demo(db: Session, keep_user_id: str | None = None) -> dict:
    """Removes demo-flagged records only. Real facilities, users and audit logs are untouched;
    demo user accounts are kept (passwords reset) so active demo sessions stay valid."""
    removed = clear_demo(db)
    created = seed_demo(db)
    return {**removed, **created}


def create_admin(db: Session, email: str, name: str, password: str) -> User:
    seed_reference(db)
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")
    u = db.query(User).filter_by(email=email.lower()).one_or_none()
    if u:
        raise SystemExit("User already exists")
    u = User(email=email.lower(), full_name=name, role=UserRole.SYSTEM_ADMIN, password_hash=hash_password(password))
    db.add(u)
    db.commit()
    return u


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "demo"
    db = SessionLocal()
    try:
        if cmd == "reference":
            seed_reference(db)
            print("Reference data seeded.")
        elif cmd == "demo":
            if db.query(Facility).filter(Facility.is_demo.is_(True)).first():
                print("Demo data already present. Use 'reset-demo' to restore the scenario.")
                seed_reference(db)
            else:
                print("Demo seeded:", seed_demo(db))
        elif cmd == "reset-demo":
            print("Demo reset:", reset_demo(db))
        elif cmd == "create-admin":
            email, name = argv[2], argv[3]
            pw = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
            create_admin(db, email, name, pw)
            print("Administrator created.")
        else:
            print(__doc__)
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv)
