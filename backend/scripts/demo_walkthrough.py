"""End-to-end walkthrough of the hackathon demo scenario against a running server.

Usage (DEMO_MODE must be on, run `python -m app.seed reset-demo` first):
    python scripts/demo_walkthrough.py [BASE_URL]

BASE_URL defaults to http://127.0.0.1:8000. Pointing it at the Vite dev server
(http://127.0.0.1:5173) also exercises the frontend proxy. All SMS are simulated
unless live Africa's Talking credentials are configured.
"""

import os
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo#2026!")
DOMAIN = "demo.stockout.example"
c = httpx.Client(base_url=BASE, timeout=30)


def step(msg: str) -> None:
    print(f"\n== {msg}")


def ok(r: httpx.Response, *codes: int) -> dict:
    if r.status_code not in (codes or (200,)):
        raise SystemExit(f"FAILED {r.request.method} {r.request.url} -> {r.status_code}: {r.text[:400]}")
    return r.json() if "json" in r.headers.get("content-type", "") else {}


def login(local: str) -> dict:
    tok = ok(c.post("/api/auth/login", json={"email": f"{local}@{DOMAIN}", "password": PASSWORD}))["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def inv_item(h: dict, med_code: str) -> dict:
    items = ok(c.get("/api/inventory", params={"q": med_code, "page_size": 50}, headers=h))["items"]
    return next(i for i in items if i["medicine"]["code"] == med_code)


def count(h: dict, inv: dict, qty: int) -> dict:
    return ok(c.post(f"/api/inventory/{inv['id']}/movements", headers=h,
                     json={"movement_type": "count", "quantity": qty, "reason": "Demo stock count",
                           "idempotency_key": uuid.uuid4().hex}), 201)


step("Health and readiness")
print(ok(c.get("/health")), ok(c.get("/ready")))
meta = ok(c.get("/api/public/meta"))
print("demo_mode:", meta["demo_mode"], "| sms_mode:", meta["sms_mode"])

step("Patient searches for Amoxicillin in Nairobi")
nairobi = next(x for x in ok(c.get("/api/locations/counties")) if x["name"] == "Nairobi")
amox = ok(c.get("/api/medicines", params={"q": "amoxicillin"}))["items"][0]
res = ok(c.get("/api/availability/search", params={"medicine_id": amox["id"], "county_id": nairobi["id"]}))
for r in res["results"]:
    print(f"  {r['facility']['name']:<40} {r['status']:<13} updated {r['age_hours']} h ago")
print("  notice:", res["notice"])

step("Pharmacist at Mwangaza records a dispense, then a count of zero")
ph = login("pharmacist.mwangaza")
item = inv_item(ph, "MED001")
out = ok(c.post(f"/api/inventory/{item['id']}/movements", headers=ph,
                json={"movement_type": "dispense", "quantity": 30, "idempotency_key": uuid.uuid4().hex,
                      "expected_version": item["version"]}), 201)
print("  after dispense:", out["item"]["quantity"], out["item"]["stock_status"])
stale = c.post(f"/api/inventory/{item['id']}/movements", headers=ph,
               json={"movement_type": "dispense", "quantity": 1, "expected_version": item["version"]})
print("  stale expected_version rejected:", stale.status_code, stale.json()["error"]["code"])
out = count(ph, item, 0)
print("  after count:", out["item"]["quantity"], out["item"]["stock_status"],
      "| alerts:", [a["alert_type"] for a in out["alerts"]])

step("Baraka also reports zero via SMS command (simulated inbound SMS)")
admin = login("admin")
# Fictional seeded SMS number for the Baraka demo admin (never a real handset).
r = ok(c.post("/api/simulator/sms", headers=admin, json={"phone": "+254700000031", "text": "STOCK MED001 0"}))
print("  SMS reply:", r.get("reply"))
baraka = login("admin.baraka")
print("  Baraka MED001 now:", inv_item(baraka, "MED001")["stock_status"])

step("Ripple Alert: regional signal across independent facilities")
ripple = ok(c.get("/api/alerts", params={"alert_type": "ripple"}, headers=admin))["items"]
assert ripple, "expected a ripple signal"
detail = ok(c.get(f"/api/alerts/{ripple[0]['id']}", headers=admin))
print("  ", detail["title"])
print("   facilities counted:", detail["evidence"]["facilities_counted"], "| score:", detail["evidence"]["score"])
for e in detail["ripple_evidence"]:
    print(f"   - {e['facility_name']:<38} {e['observed_status']:<14} weight={e['weight']} counted={e['counted']}")
print("   interpretation:", detail["evidence"]["interpretation"])
ok(c.post(f"/api/alerts/{detail['id']}/investigate", headers=admin, json={"note": "Calling suppliers"}))
print("   status -> investigating")

step("USSD: patient finds medicine and reports unavailability")
sid = "demo-" + uuid.uuid4().hex[:8]
phone = "+254700000999"
for text in ["", "1"]:
    r = ok(c.post("/api/simulator/ussd", json={"session_id": sid, "phone": phone, "text": text}))
    print("  >", repr(text), "\n   ", r["response"].replace("\n", "\n    "))

step("Notification history (no message is shown as delivered without a delivery report)")
hist = ok(c.get("/api/notifications/history", headers=admin, params={"page_size": 100}))["items"]
by_status: dict[str, int] = {}
for d in hist:
    by_status[d["status"]] = by_status.get(d["status"], 0) + 1
print("  ", by_status, "| sample recipient:", hist[0]["recipient"] if hist else None)

step("Role checks")
staff = login("staff.mwangaza")
print("  staff -> audit logs:", c.get("/api/admin/audit-logs", headers=staff).status_code)
print("  facility admin -> resolve ripple:",
      c.post(f"/api/alerts/{detail['id']}/resolve", headers=ph, json={"resolution_notes": "not mine"}).status_code)
ok(c.post(f"/api/alerts/{detail['id']}/resolve", headers=admin,
          json={"resolution_notes": "Supplier delay confirmed; resupply scheduled"}))
print("  system admin resolved ripple signal")

print("\nWalkthrough completed.")
