from tests.conftest import login
from tests.helpers import facility, item, medicine


def test_login_and_me(client, admin_h):
    r = client.get("/api/auth/me", headers=admin_h)
    assert r.status_code == 200
    assert r.json()["role"] == "system_admin"
    assert "password_hash" not in r.text


def test_bad_password_rejected(client):
    r = client.post("/api/auth/login", json={"email": "admin@demo.stockout.example", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_logout_revokes_token(client, admin_h):
    assert client.post("/api/auth/logout", headers=admin_h).status_code == 204
    assert client.get("/api/auth/me", headers=admin_h).status_code == 401


def test_anonymous_patient_cannot_modify_inventory(client, db):
    inv = item(db, "FAC-D001", "MED001")
    r = client.post(f"/api/inventory/{inv.id}/movements", json={"movement_type": "count", "quantity": 0})
    assert r.status_code == 401
    r = client.post("/api/inventory", json={"facility_id": inv.facility_id, "medicine_id": inv.medicine_id,
                                            "quantity": 1, "min_threshold": 0})
    assert r.status_code == 401
    assert client.get("/api/inventory").status_code == 401


def test_facility_isolation(client, db, mwangaza_h):
    other = item(db, "FAC-D002", "MED001")
    assert client.get(f"/api/inventory/{other.id}", headers=mwangaza_h).status_code == 404
    r = client.post(f"/api/inventory/{other.id}/movements", json={"movement_type": "count", "quantity": 0},
                    headers=mwangaza_h)
    assert r.status_code == 404
    listing = client.get("/api/inventory", headers=mwangaza_h).json()
    own = facility(db, "FAC-D001").id
    assert listing["total"] > 0 and all(i["facility_id"] == own for i in listing["items"])
    assert client.get(f"/api/inventory?facility_id={other.facility_id}", headers=mwangaza_h).status_code == 404


def test_staff_cannot_approve_or_manage_catalog(client, db, mwangaza_h):
    f = facility(db, "FAC-D006")
    assert client.post(f"/api/admin/facilities/{f.id}/approve", headers=mwangaza_h).status_code == 403
    r = client.post("/api/admin/medicines", headers=mwangaza_h, json={
        "code": "MED999", "generic_name": "Test", "strength": "1 mg", "dosage_form": "tablet", "base_unit": "tablet"})
    assert r.status_code == 403
    assert client.get("/api/admin/audit-logs", headers=mwangaza_h).status_code == 403


def test_staff_without_stock_permission_blocked(client, db, mwangaza_h):
    clerk = login(client, "staff.mwangaza")
    members = client.get(f"/api/manage/facilities/{facility(db, 'FAC-D001').id}/staff", headers=mwangaza_h).json()
    clerk_m = next(m for m in members if m["email"].startswith("staff."))
    r = client.patch(f"/api/manage/facilities/{facility(db, 'FAC-D001').id}/staff/{clerk_m['id']}",
                     json={"can_update_stock": False}, headers=mwangaza_h)
    assert r.status_code == 200
    inv = item(db, "FAC-D001", "MED002")
    r = client.post(f"/api/inventory/{inv.id}/movements", json={"movement_type": "count", "quantity": 5},
                    headers=clerk)
    assert r.status_code == 403
    # Staff can't manage other staff
    assert client.post(f"/api/manage/facilities/{facility(db, 'FAC-D001').id}/staff", headers=clerk, json={
        "full_name": "X Person", "email": "x@example.com", "password": "longenoughpw1"}).status_code == 403


def test_pending_facility_not_public_until_approved(client, db, admin_h):
    f = facility(db, "FAC-D006")
    assert client.get(f"/api/facilities/{f.id}").status_code == 404
    assert client.post(f"/api/admin/facilities/{f.id}/approve", headers=admin_h).status_code == 200
    assert client.get(f"/api/facilities/{f.id}").status_code == 200
    r = client.post(f"/api/admin/facilities/{f.id}/suspend", json={"reason": "Licence review"}, headers=admin_h)
    assert r.status_code == 200
    assert client.get(f"/api/facilities/{f.id}").status_code == 404
    logs = client.get("/api/admin/audit-logs?action=facility", headers=admin_h).json()["items"]
    assert {"facility.approved", "facility.suspended"} <= {l["action"] for l in logs}


def test_public_facility_hides_private_fields(client, db):
    f = facility(db, "FAC-D001")
    body = client.get(f"/api/facilities/{f.id}").json()
    assert "internal_notes" not in str(body) and "license_number" not in body
    assert body["availability"]
    med = medicine(db, "MED001")
    s = client.get(f"/api/availability/search?medicine_id={med.id}").json()
    assert "internal_notes" not in str(s)


def test_registration_creates_pending_facility(client):
    counties = client.get("/api/locations/counties").json()
    nairobi = next(c for c in counties if c["name"] == "Nairobi")
    r = client.post("/api/facilities/register", json={
        "name": "Test Registration Pharmacy", "facility_type": "pharmacy", "county_id": nairobi["id"],
        "admin_full_name": "Reg Admin", "admin_email": "reg@example.com", "admin_password": "a-long-password",
        "admin_phone": "0712345678", "accept_terms": True})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    h = {"Authorization": "Bearer " + client.post("/api/auth/login", json={
        "email": "reg@example.com", "password": "a-long-password"}).json()["access_token"]}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["memberships"][0]["facility_status"] == "pending"
