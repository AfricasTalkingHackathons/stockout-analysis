from datetime import timedelta

from app.database import utcnow
from app.models import Alert, MovementType, NotificationDelivery, StockMovement
from app.services.alerts import estimate_days_remaining, run_periodic_checks
from app.services.runtime_config import get_config
from tests.conftest import login
from tests.helpers import facility, item, medicine, set_count


def _alerts(db, **kw):
    db.expire_all()
    return db.query(Alert).filter_by(**kw).all()


def test_zero_stock_creates_single_stockout_alert(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")
    assert set_count(client, mwangaza_h, inv.id, 0).status_code == 201
    assert set_count(client, mwangaza_h, inv.id, 0).status_code == 201  # repeat -> no duplicate alert
    open_ = [a for a in _alerts(db, inventory_id=inv.id, alert_type="stockout") if a.status == "open"]
    assert len(open_) == 1 and open_[0].severity == "critical"
    sms = db.query(NotificationDelivery).filter_by(alert_id=open_[0].id).all()
    assert sms and all(d.status in ("queued", "simulated") for d in sms)


def test_recovery_auto_resolves(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")
    set_count(client, mwangaza_h, inv.id, 0)
    set_count(client, mwangaza_h, inv.id, 2000)
    a = _alerts(db, inventory_id=inv.id, alert_type="stockout")[0]
    assert a.status == "resolved" and a.resolution_notes.startswith("Auto-resolved")


def test_low_stock_alert(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")  # min 500
    set_count(client, mwangaza_h, inv.id, 400)
    assert [a.status for a in _alerts(db, inventory_id=inv.id, alert_type="low_stock")] == ["open"]


def test_days_remaining_estimate(db):
    cfg = get_config(db)
    est = estimate_days_remaining(db, item(db, "FAC-D001", "MED001"), cfg)
    assert est.avg_daily is not None and 20 < est.avg_daily < 30
    assert est.days_remaining is not None and 13 < est.days_remaining < 20


def test_insufficient_history_gives_no_estimate(db):
    est = estimate_days_remaining(db, item(db, "FAC-D003", "MED001"))
    assert est.days_remaining is None and "Insufficient" in est.reason


def test_zero_consumption_no_estimate(db):
    inv = item(db, "FAC-D003", "MED013")
    old = utcnow() - timedelta(days=20)
    db.query(StockMovement).filter_by(inventory_id=inv.id).update({"created_at": old})
    for d in range(3):
        db.add(StockMovement(inventory_id=inv.id, movement_type=MovementType.DISPENSE, quantity_delta=0,
                             quantity_before=inv.quantity, quantity_after=inv.quantity, source="test",
                             created_at=old + timedelta(days=d + 1)))
    db.commit()
    est = estimate_days_remaining(db, inv)
    assert est.days_remaining is None and est.avg_daily == 0.0


def test_early_warning_from_consumption(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED001")  # ~25/day
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "dispense", "quantity": 250})  # 150 left > min 100, ~6 days
    assert r.status_code == 201
    ew = _alerts(db, inventory_id=inv.id, alert_type="early_warning")
    assert ew and ew[0].evidence["estimated_days_remaining"] < 7


def test_ripple_requires_independent_verified_evidence(client, db, mwangaza_h):
    med = medicine(db, "MED001")
    nairobi = facility(db, "FAC-D001").county_id
    # Facility A to zero (Tumaini B is already low and fresh)
    set_count(client, mwangaza_h, item(db, "FAC-D001", "MED001").id, 0)
    assert not _alerts(db, alert_type="ripple")
    # Two unverified public reports for Baraka (C) - duplicates count once and are down-weighted
    baraka = facility(db, "FAC-D003")
    reps = []
    for token in ("tok-aaaaaaaa", "tok-bbbbbbbb"):
        r = client.post("/api/reports/stockout", json={"facility_id": baraka.id, "medicine_id": med.id,
                                                      "client_token": token})
        assert r.status_code == 201
        reps.append(r.json()["reference"])
    assert not _alerts(db, alert_type="ripple"), "unverified reports must not trigger alone"
    # Baraka verifies one report -> ripple triggers
    baraka_h = login(client, "admin.baraka")
    rep = client.get("/api/reports/stockout?verification_status=unverified", headers=baraka_h).json()["items"][0]
    assert client.post(f"/api/reports/{rep['id']}/verify", json={"decision": "verified"},
                       headers=baraka_h).status_code == 200
    ripple = _alerts(db, alert_type="ripple")
    assert len(ripple) == 1
    a = ripple[0]
    assert a.county_id == nairobi and a.evidence["facilities_counted"] == 3
    counted = [e for e in a.ripple_evidence if e.counted]
    assert len({e.facility_id for e in counted}) == len(counted) == 3
    assert "Not a confirmed" in a.evidence["interpretation"]
    # Re-evaluation doesn't duplicate
    set_count(client, mwangaza_h, item(db, "FAC-D001", "MED001").id, 0)
    assert len(_alerts(db, alert_type="ripple")) == 1


def test_ripple_excludes_stale_and_rejected(client, db, admin_h):
    med = medicine(db, "MED001")
    # Upendo (stale, 10 days) reports zero via old inventory -> outside window, not counted
    up = item(db, "FAC-D004", "MED001")
    up.quantity = 0
    db.commit()
    from app.services.alerts import run_ripple
    assert run_ripple(db, med.id, facility(db, "FAC-D004").county_id) is None


def test_ripple_workflow_and_detail(client, db, admin_h, mwangaza_h):
    from tests.conftest import login
    set_count(client, mwangaza_h, item(db, "FAC-D001", "MED001").id, 0)
    set_count(client, login(client, "admin.baraka"), item(db, "FAC-D003", "MED001").id, 0)
    ripple = client.get("/api/alerts?alert_type=ripple", headers=admin_h).json()["items"]
    assert len(ripple) == 1
    aid = ripple[0]["id"]
    detail = client.get(f"/api/alerts/{aid}", headers=admin_h).json()
    assert len(detail["ripple_evidence"]) >= 3
    # facility admin can see but cannot resolve the ripple signal
    assert client.get(f"/api/alerts/{aid}", headers=mwangaza_h).status_code == 200
    assert client.post(f"/api/alerts/{aid}/resolve", json={"resolution_notes": "x fixed"},
                       headers=mwangaza_h).status_code == 403
    assert client.post(f"/api/alerts/{aid}/investigate", headers=admin_h).json()["status"] == "investigating"
    r = client.post(f"/api/alerts/{aid}/resolve", headers=admin_h,
                    json={"resolution_notes": "Supplier delay confirmed; resupply scheduled"})
    assert r.json()["status"] == "resolved" and r.json()["resolution_notes"].startswith("Supplier")


def test_acknowledge_and_resolve(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")
    alert = set_count(client, mwangaza_h, inv.id, 0).json()["alerts"][0]
    r = client.post(f"/api/alerts/{alert['id']}/acknowledge", headers=mwangaza_h)
    assert r.json()["status"] == "acknowledged" and r.json()["assigned_to"]
    assert client.post(f"/api/alerts/{alert['id']}/acknowledge", headers=mwangaza_h).status_code == 409
    assert client.post(f"/api/alerts/{alert['id']}/resolve", headers=mwangaza_h,
                       json={"resolution_notes": ""}).status_code == 422
    r = client.post(f"/api/alerts/{alert['id']}/resolve", headers=mwangaza_h,
                    json={"resolution_notes": "Emergency order received"})
    assert r.json()["status"] == "resolved"


def test_stale_check_creates_alert_and_request(db):
    out = run_periodic_checks(db)
    assert out["stale"] >= 1
    stale = _alerts(db, alert_type="stale_report")
    assert any(a.facility_id == facility(db, "FAC-D004").id for a in stale)
    assert db.query(NotificationDelivery).filter_by(purpose="alert_stale_report").count() >= 1
    # Running again doesn't duplicate
    run_periodic_checks(db)
    assert len(_alerts(db, alert_type="stale_report")) == len(stale)


def test_expiring_check(db):
    run_periodic_checks(db)
    assert _alerts(db, alert_type="expiring")


def test_escalation(db):
    a = Alert(alert_type="stockout", severity="critical", dedupe_key="x", title="t",
              facility_id=facility(db, "FAC-D001").id, created_at=utcnow() - timedelta(hours=30))
    db.add(a)
    db.commit()
    run_periodic_checks(db)
    db.refresh(a)
    assert a.escalation_level == 1
