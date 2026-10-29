from app.models import AuditLog, Facility, InventoryItem, User
from app.seed import reset_demo
from app.security import hash_password
from tests.helpers import facility, item, set_count


def test_dashboard_reflects_database(client, db, admin_h, mwangaza_h):
    before = client.get("/api/admin/overview", headers=admin_h).json()
    db_items = db.query(InventoryItem).count()
    assert before["totals"]["medicine_records"] == db_items
    assert before["has_demo_data"] is True
    set_count(client, mwangaza_h, item(db, "FAC-D001", "MED002").id, 0)
    after = client.get("/api/admin/overview", headers=admin_h).json()
    assert after["totals"]["out_of_stock"] == before["totals"]["out_of_stock"] + 1
    assert after["totals"]["unresolved_alerts"] > before["totals"]["unresolved_alerts"]
    assert after["recent_movements"][0]["quantity_after"] == 0
    assert any(t["stockout"] for t in after["trend"])
    assert after["platform"]["pending_facilities"] == 1


def test_facility_dashboard_scoped(client, db, mwangaza_h):
    ov = client.get("/api/dashboard/overview", headers=mwangaza_h).json()
    names = {m["facility_name"] for m in ov["attention"]} | {r["name"] for r in ov["facility_comparison"]}
    assert all("Mwangaza" in n for n in names)
    other = facility(db, "FAC-D002").id
    assert client.get(f"/api/dashboard/overview?facility_id={other}", headers=mwangaza_h).status_code == 404
    assert client.get("/api/admin/overview", headers=mwangaza_h).status_code == 403


def test_dashboard_filters(client, db, admin_h):
    kiambu = facility(db, "FAC-D005").county_id
    ov = client.get(f"/api/admin/overview?county_id={kiambu}", headers=admin_h).json()
    assert ov["totals"]["facilities"] == 1
    ov = client.get("/api/admin/overview?status=stale", headers=admin_h).json()
    assert ov["attention"] and all(a["status"] == "stale" for a in ov["attention"])


def test_demo_reset_preserves_real_data(client, db, admin_h, mwangaza_h):
    real = Facility(code="FAC-9999", name="Real Facility", facility_type="pharmacy", county_id=1, status="approved")
    real_user = User(email="real@example.org", full_name="Real User", role="facility_admin",
                     password_hash=hash_password("x" * 12))
    db.add_all([real, real_user])
    db.commit()
    set_count(client, mwangaza_h, item(db, "FAC-D001", "MED001").id, 0)
    r = client.post("/api/admin/demo/reset", headers=admin_h)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Facility).filter_by(code="FAC-9999").one()
    assert db.query(User).filter_by(email="real@example.org").one()
    assert item(db, "FAC-D001", "MED001").quantity == 400
    assert db.query(AuditLog).filter_by(action="demo.reset").count() == 1
    # the admin session survives the reset
    assert client.get("/api/auth/me", headers=admin_h).status_code == 200
    # reset is repeatable / predictable
    reset_demo(db)
    assert db.query(Facility).filter_by(is_demo=True).count() == 6


def test_demo_reset_requires_admin(client, mwangaza_h):
    assert client.post("/api/admin/demo/reset", headers=mwangaza_h).status_code == 403


def test_validation_error_format(client, mwangaza_h, db):
    inv = item(db, "FAC-D001", "MED001")
    r = client.post(f"/api/inventory/{inv.id}/movements", json={"movement_type": "teleport", "quantity": 1},
                    headers=mwangaza_h)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and err["details"]
    r = client.post("/api/notifications/subscriptions", json={"phone": "123", "medicine_id": "x", "county_id": 1,
                                                              "consent": True})
    assert r.status_code == 422


def test_unknown_route_404_json(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_health_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"


def test_rate_limit(client, monkeypatch):
    from app.config import get_settings
    from app.ratelimit import limiter
    limiter.reset()
    monkeypatch.setattr(get_settings(), "rate_limit_sensitive_per_minute", 2)
    codes = [client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}).status_code for _ in range(3)]
    assert codes[-1] == 429


def test_report_lookup_and_public_report(client, db):
    f = facility(db, "FAC-D003")
    med = item(db, "FAC-D003", "MED001").medicine_id
    r = client.post("/api/reports/stockout", json={"facility_id": f.id, "medicine_id": med,
                                                   "client_token": "abcdefgh1"})
    ref = r.json()["reference"]
    again = client.post("/api/reports/stockout", json={"facility_id": f.id, "medicine_id": med,
                                                       "client_token": "abcdefgh1"})
    assert again.json()["duplicate"] is True and again.json()["reference"] == ref
    pub = client.get(f"/api/reports/lookup/{ref}").json()
    assert pub["verification_status"] == "unverified" and "comment" not in pub
    pending = facility(db, "FAC-D006")
    r = client.post("/api/reports/stockout", json={"facility_id": pending.id, "medicine_id": med})
    assert r.status_code == 404
