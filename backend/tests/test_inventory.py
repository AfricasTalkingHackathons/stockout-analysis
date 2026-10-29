from app.models import AuditLog, StockMovement
from tests.helpers import facility, item, medicine, set_count


def test_movements_recorded_and_audited(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "receipt", "quantity": 500, "reason": "Delivery note 42"})
    assert r.status_code == 201, r.text
    assert r.json()["item"]["quantity"] == 3000
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "dispense", "quantity": 100})
    assert r.json()["item"]["quantity"] == 2900
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "adjustment", "quantity": -10, "reason": "Damaged"})
    assert r.json()["item"]["quantity"] == 2890
    hist = client.get(f"/api/inventory/{inv.id}/history", headers=mwangaza_h).json()
    types = [m["movement_type"] for m in hist["movements"]["items"]]
    assert types[:3] == ["adjustment", "dispense", "receipt"] and "initial" in types
    assert hist["levels"][-1]["quantity"] == 2890
    db.expire_all()
    assert db.query(AuditLog).filter(AuditLog.entity_id == inv.id).count() >= 4


def test_negative_stock_rejected(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED008")  # 12 inhalers
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "dispense", "quantity": 13})
    assert r.status_code == 400 and r.json()["error"]["code"] == "insufficient_stock"
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "adjustment", "quantity": -20, "reason": "x"})
    assert r.status_code == 400
    assert set_count(client, mwangaza_h, inv.id, -1).status_code == 400
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "receipt", "quantity": 0})
    assert r.status_code == 400
    db.expire_all()
    assert item(db, "FAC-D001", "MED008").quantity == 12


def test_idempotent_movement(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")
    body = {"movement_type": "dispense", "quantity": 10, "idempotency_key": "client-key-123456"}
    r1 = client.post(f"/api/inventory/{inv.id}/movements", json=body, headers=mwangaza_h)
    r2 = client.post(f"/api/inventory/{inv.id}/movements", json=body, headers=mwangaza_h)
    assert r1.status_code == r2.status_code == 201
    assert r2.json()["duplicate"] is True
    assert r1.json()["movement"]["id"] == r2.json()["movement"]["id"]
    db.expire_all()
    assert item(db, "FAC-D001", "MED002").quantity == 2490
    assert db.query(StockMovement).filter_by(idempotency_key="client-key-123456").count() == 1


def test_version_conflict(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")
    v = inv.version
    assert client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                       json={"movement_type": "dispense", "quantity": 1, "expected_version": v}).status_code == 201
    r = client.post(f"/api/inventory/{inv.id}/movements", headers=mwangaza_h,
                    json={"movement_type": "dispense", "quantity": 1, "expected_version": v})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


def test_create_inventory_validation(client, db, mwangaza_h):
    f = facility(db, "FAC-D001")
    ibu = medicine(db, "MED013")
    r = client.post("/api/inventory", headers=mwangaza_h, json={
        "facility_id": f.id, "medicine_id": ibu.id, "quantity": 50, "min_threshold": 20, "unit": "box"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unit_mismatch"
    r = client.post("/api/inventory", headers=mwangaza_h, json={
        "facility_id": f.id, "medicine_id": ibu.id, "quantity": -5, "min_threshold": 20})
    assert r.status_code == 422
    r = client.post("/api/inventory", headers=mwangaza_h, json={
        "facility_id": f.id, "medicine_id": ibu.id, "quantity": 50, "min_threshold": 20})
    assert r.status_code == 201
    r = client.post("/api/inventory", headers=mwangaza_h, json={
        "facility_id": f.id, "medicine_id": ibu.id, "quantity": 50, "min_threshold": 20})
    assert r.status_code == 409


def test_inventory_filters_and_export(client, db, mwangaza_h):
    low = client.get("/api/inventory?status=low", headers=mwangaza_h).json()
    assert all(i["stock_status"] == "low" for i in low["items"])
    r = client.get("/api/inventory/export.csv", headers=mwangaza_h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "Mwangaza" in r.text and "Tumaini" not in r.text
    from tests.conftest import login
    assert client.get("/api/inventory/export.csv", headers=login(client, "staff.mwangaza")).status_code == 403


def test_threshold_patch_triggers_low(client, db, mwangaza_h):
    inv = item(db, "FAC-D001", "MED002")
    r = client.patch(f"/api/inventory/{inv.id}", headers=mwangaza_h, json={"min_threshold": 3000})
    assert r.status_code == 200 and r.json()["stock_status"] == "low"
    alerts = client.get("/api/alerts?status=active&alert_type=low_stock", headers=mwangaza_h).json()["items"]
    assert any(a["medicine"]["code"] == "MED002" for a in alerts)
