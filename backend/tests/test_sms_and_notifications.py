import httpx

from app.config import get_settings
from app.models import DeliveryStatus, NotificationDelivery, NotificationSubscription, StockMovement
from app.services.notifications import apply_delivery_report, attempt_delivery, dispatch_due, queue_sms
from app.services.sms_providers import (
    AfricasTalkingProvider,
    SendResult,
    SimulatedProvider,
    SmsProvider,
    set_provider_override,
)
from tests.helpers import facility, item, medicine, set_count

STAFF = "+254700000011"  # demo Mwangaza pharmacist sms_phone


def inbound(client, text, sender=STAFF, msg_id="ATXid_1"):
    return client.post("/api/webhooks/sms", data={"from": sender, "to": "12345", "text": text, "id": msg_id,
                                                  "date": "2026-10-29 10:00:00"})


def test_sms_stock_command_updates_inventory(client, db):
    r = inbound(client, "STOCK MED001 12")
    assert r.status_code == 200 and r.json()["outcome"] == "recorded"
    db.expire_all()
    inv = item(db, "FAC-D001", "MED001")
    assert inv.quantity == 12
    mv = db.query(StockMovement).filter_by(idempotency_key="sms:ATXid_1").one()
    assert mv.source == "sms" and mv.movement_type == "count"
    reply = db.query(NotificationDelivery).filter_by(purpose="sms_command_reply").one()
    assert "recorded as 12" in reply.message


def test_duplicate_sms_callback_processed_once(client, db):
    inbound(client, "STOCK MED001 12", msg_id="dup-1")
    r = inbound(client, "STOCK MED001 12", msg_id="dup-1")
    assert r.json()["duplicate"] is True
    db.expire_all()
    inv = item(db, "FAC-D001", "MED001")
    assert db.query(StockMovement).filter_by(inventory_id=inv.id, movement_type="count").count() == 1
    assert db.query(NotificationDelivery).filter_by(purpose="sms_command_reply").count() == 1


def test_unauthorised_sender_rejected(client, db):
    r = inbound(client, "STOCK MED001 0", sender="+254799999999", msg_id="u1")
    assert r.json()["outcome"] == "unauthorised"
    db.expire_all()
    assert item(db, "FAC-D001", "MED001").quantity == 400


def test_malformed_and_unknown(client):
    assert inbound(client, "STOCK MED001", msg_id="m1").json()["outcome"] == "malformed"
    assert inbound(client, "STOCK MED001 -4", msg_id="m2").json()["outcome"] == "invalid_quantity"
    assert inbound(client, "STOCK MED777 4", msg_id="m3").json()["outcome"] == "unknown_medicine"
    assert inbound(client, "STOCK MED013 4", msg_id="m4").json()["outcome"] == "no_inventory"
    assert inbound(client, "HELLO", msg_id="m5").json()["outcome"] == "unrecognised"


def test_suspended_facility_staff_cannot_update(client, db, admin_h):
    f = facility(db, "FAC-D001")
    client.post(f"/api/admin/facilities/{f.id}/suspend", json={"reason": "test"}, headers=admin_h)
    assert inbound(client, "STOCK MED001 1", msg_id="s1").json()["outcome"] == "unauthorised"


def test_stop_unsubscribes(client, db):
    med = medicine(db, "MED001")
    county = facility(db, "FAC-D001").county_id
    r = client.post("/api/notifications/subscriptions",
                    json={"phone": "0712000222", "medicine_id": med.id, "county_id": county, "consent": True})
    assert r.status_code == 201 and "*" in r.json()["phone"]
    assert inbound(client, "stop", sender="+254712000222", msg_id="stop1").json()["outcome"] == "unsubscribed"
    db.expire_all()
    assert db.query(NotificationSubscription).filter_by(phone="+254712000222", is_active=True).count() == 0


def test_subscription_requires_consent(client, db):
    med = medicine(db, "MED001")
    r = client.post("/api/notifications/subscriptions",
                    json={"phone": "0712000222", "medicine_id": med.id, "county_id": 1, "consent": False})
    assert r.status_code == 422


def test_subscriber_notified_when_available(client, db, mwangaza_h):
    med = medicine(db, "MED001")
    county = facility(db, "FAC-D001").county_id
    client.post("/api/notifications/subscriptions",
                json={"phone": "0712000333", "medicine_id": med.id, "county_id": county, "consent": True})
    inv = item(db, "FAC-D001", "MED001")
    set_count(client, mwangaza_h, inv.id, 0)
    set_count(client, mwangaza_h, inv.id, 300)
    db.expire_all()
    msgs = db.query(NotificationDelivery).filter_by(purpose="availability_update", recipient="+254712000333").all()
    assert len(msgs) == 1 and "Reply STOP" in msgs[0].message
    # cooldown: another restock doesn't spam
    set_count(client, mwangaza_h, inv.id, 0)
    set_count(client, mwangaza_h, inv.id, 300)
    db.expire_all()
    assert db.query(NotificationDelivery).filter_by(purpose="availability_update").count() == 1


def test_demo_mode_without_credentials_simulates(db):
    d = queue_sms(db, "+254712000444", "hello", "test")
    db.flush()
    attempt_delivery(db, d)
    assert d.status == DeliveryStatus.SIMULATED and d.provider == "simulated"
    assert d.status != DeliveryStatus.DELIVERED


class FlakyProvider(SmsProvider):
    name = "flaky"

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def send(self, to, message):
        self.calls += 1
        return self.results.pop(0)


def test_retry_then_accept(db):
    set_provider_override(FlakyProvider([
        SendResult(False, True, "flaky", error="timeout"),
        SendResult(True, False, "flaky", message_id="ATPid_9", provider_status="Success"),
    ]))
    d = queue_sms(db, "+254712000555", "hello", "test")
    db.commit()
    dispatch_due(db)
    db.refresh(d)
    assert d.status == DeliveryStatus.RETRYING and d.attempts == 1
    d.next_attempt_at = None
    db.commit()
    dispatch_due(db)
    db.refresh(d)
    assert d.status == DeliveryStatus.ACCEPTED  # accepted, NOT delivered
    assert apply_delivery_report(db, "ATPid_9", "Success", None)
    assert d.status == DeliveryStatus.DELIVERED and d.delivered_at


def test_permanent_failure_not_reported_as_success(db):
    set_provider_override(FlakyProvider([SendResult(False, False, "flaky", error="Provider status 403 InvalidPhone")]))
    d = queue_sms(db, "+254712000666", "hello", "test")
    db.commit()
    dispatch_due(db)
    db.refresh(d)
    assert d.status == DeliveryStatus.FAILED and "403" in d.failure_reason


def test_retries_exhausted(db):
    n = get_settings().sms_max_attempts
    set_provider_override(FlakyProvider([SendResult(False, True, "flaky", error="5xx")] * n))
    d = queue_sms(db, "+254712000777", "hello", "test")
    db.commit()
    for _ in range(n):
        d.next_attempt_at = None
        db.commit()
        dispatch_due(db)
        db.refresh(d)
    assert d.status == DeliveryStatus.FAILED and d.attempts == n


def test_delivery_report_webhook_failed_and_idempotent(client, db):
    d = queue_sms(db, "+254712000888", "hello", "test")
    d.provider_message_id, d.status = "ATPid_X", DeliveryStatus.ACCEPTED
    db.commit()
    for _ in range(2):
        r = client.post("/api/webhooks/delivery-report",
                        data={"id": "ATPid_X", "status": "Failed", "failureReason": "UserInBlacklist",
                              "phoneNumber": "+254712000888"})
        assert r.status_code == 200 and r.json()["matched"]
    # A late "Sent" must not downgrade a terminal failure
    client.post("/api/webhooks/delivery-report", data={"id": "ATPid_X", "status": "Sent"})
    db.expire_all()
    d = db.get(NotificationDelivery, d.id)
    assert d.status == DeliveryStatus.FAILED and d.failure_reason == "UserInBlacklist"


def _at_provider(handler):
    s = get_settings().model_copy(update={"at_username": "sandbox", "at_api_key": "k", "at_environment": "sandbox"})
    return AfricasTalkingProvider(s, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_africastalking_provider_request_and_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["apiKey"]
        seen["body"] = request.content.decode()
        return httpx.Response(201, json={"SMSMessageData": {"Message": "Sent to 1/1", "Recipients": [
            {"statusCode": 101, "number": "+254712000999", "status": "Success", "cost": "KES 0.8",
             "messageId": "ATXid_abc"}]}})

    res = _at_provider(handler).send("+254712000999", "hi")
    assert res.accepted and res.message_id == "ATXid_abc" and not res.simulated
    assert seen["url"] == "https://api.sandbox.africastalking.com/version1/messaging"
    assert seen["key"] == "k" and "username=sandbox" in seen["body"]


def test_africastalking_provider_failures():
    def rejected(_):
        return httpx.Response(201, json={"SMSMessageData": {"Message": "x", "Recipients": [
            {"statusCode": 403, "number": "+254", "status": "InvalidPhoneNumber", "messageId": "None"}]}})

    r = _at_provider(rejected).send("+254712000999", "hi")
    assert not r.accepted and not r.retryable

    def gateway(_):
        return httpx.Response(503, text="down")

    r = _at_provider(gateway).send("+254712000999", "hi")
    assert not r.accepted and r.retryable

    def timeout(_):
        raise httpx.ReadTimeout("slow")

    r = _at_provider(timeout).send("+254712000999", "hi")
    assert not r.accepted and r.retryable and "timed out" in r.error


def test_demo_allowlist_keeps_live_sms_safe(monkeypatch):
    from app.services.sms_providers import provider_for
    s = get_settings().model_copy(update={"at_username": "u", "at_api_key": "k", "demo_mode": True,
                                          "demo_sms_allowlist": "+254712000001"})
    assert isinstance(provider_for(s, "+254799000000"), SimulatedProvider)
    assert isinstance(provider_for(s, "+254712000001"), AfricasTalkingProvider)


def test_test_sms_endpoint_and_history(client, admin_h):
    r = client.post("/api/notifications/test", json={"phone": "0712000123"}, headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "simulated"
    h = client.get("/api/notifications/history", headers=admin_h).json()
    assert h["total"] >= 1 and "*" in h["items"][0]["recipient"]


def test_sms_summary_endpoint(client, db):
    med = medicine(db, "MED001")
    r = client.post("/api/availability/sms-summary",
                    json={"phone": "0712000124", "medicine_id": med.id, "county_id": facility(db, "FAC-D001").county_id})
    assert r.status_code == 202 and r.json()["simulated"] is True and "[DEMO]" in r.json()["preview"]
