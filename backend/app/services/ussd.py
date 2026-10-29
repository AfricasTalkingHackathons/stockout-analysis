"""USSD flow for Africa's Talking.

Africa's Talking POSTs sessionId, serviceCode, phoneNumber, networkCode and `text`, where `text`
is every input of the session joined by '*'. A response starting with "CON " continues the session,
"END " terminates it.

The flow is deterministic: the full input path is replayed through the state machine on every
request, so retries, out-of-order delivery after a restart, or unknown session IDs still produce the
correct screen. Side effects (reports, subscriptions, SMS) only run for the final input of a request
and use per-session dedupe keys, so a repeated callback never duplicates them. The resulting state is
persisted on the session row for monitoring and timeout handling.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import utcnow
from app.models import (
    County,
    Facility,
    FacilityStatus,
    Medicine,
    NotificationSubscription,
    PickupSchedule,
    ReportedStatus,
    SearchRequest,
    UssdSession,
)
from app.security import hash_identifier
from app.services.availability import medicine_query, search_availability
from app.services.notifications import queue_sms
from app.services.reports import create_stock_report
from app.utils import normalize_ke_phone

log = logging.getLogger("stockout.ussd")

MAX_LEN = 182
PAGE = 4
SHORT = {"available": "AVAIL", "low": "LOW", "out_of_stock": "OUT", "stale": "STALE?", "unknown": "UNKNOWN"}


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "."


def _age(ts) -> str:
    if ts is None:
        return "no data"
    h = (utcnow() - ts).total_seconds() / 3600
    if h < 1:
        return "<1h"
    if h < 48:
        return f"{int(h)}h"
    return f"{int(h // 24)}d"


@dataclass
class Ctx:
    db: Session
    session_id: str
    phone: str
    simulated: bool
    state: dict = field(default_factory=lambda: {"screen": "main"})
    end: str | None = None
    error: str | None = None


class Flow:
    def __init__(self, ctx: Ctx) -> None:
        self.c = ctx
        self.db = ctx.db

    # ------------------------------------------------------------------ list helpers
    def counties(self) -> list[tuple[int, str]]:
        rows = (
            self.db.query(County)
            .join(Facility, Facility.county_id == County.id)
            .filter(Facility.status == FacilityStatus.APPROVED)
            .distinct()
            .order_by(County.name)
            .all()
        )
        return [(c.id, c.name) for c in rows]

    def medicines(self, q: str) -> list[tuple[str, str]]:
        return [(m.id, f"{m.generic_name} {m.strength}") for m in medicine_query(self.db, q).limit(16)]

    def facilities(self, county_id: int) -> list[tuple[str, str]]:
        rows = (
            self.db.query(Facility)
            .filter(Facility.county_id == county_id, Facility.status == FacilityStatus.APPROVED)
            .order_by(Facility.name)
            .all()
        )
        return [(f.id, f.name) for f in rows]

    def results(self) -> list[dict]:
        med = self.db.get(Medicine, self.c.state["med"])
        return search_availability(self.db, [med], county_id=self.c.state["county"])

    def list_items(self) -> list[tuple]:
        s = self.c.state
        sc = s["screen"]
        if sc in ("find_county", "rep_county", "sub_county", "pick_county"):
            return self.counties()
        if sc in ("find_med_select", "rep_med_select", "sub_med_select", "pick_med_select"):
            return self.medicines(s["q"])
        if sc == "rep_facility":
            return self.facilities(s["county"])
        if sc == "find_results":
            return [(r["facility"]["id"], f"{_cut(r['facility']['name'], 20)} {SHORT[r['status']]} {_age(r['last_updated_at'])}")
                    for r in self.results()]
        return []

    # ------------------------------------------------------------------ transitions
    def go(self, screen: str, **kw) -> None:
        keep = ("med", "county", "q", "facility", "flow", "pickup_in", "interval")
        self.c.state = {k: v for k, v in self.c.state.items() if k in keep}
        self.c.state.update(kw)
        self.c.state["screen"] = screen
        self.c.state["page"] = 0

    def home(self) -> None:
        self.c.state = {"screen": "main"}

    def handle(self, raw: str, is_last: bool) -> None:
        self.c.error = None
        inp = raw.strip()
        s = self.c.state
        sc = s["screen"]

        if sc == "main":
            nxt = {"1": ("find_county", "find"), "2": ("rep_med_entry", "rep"), "3": ("alerts_menu", "sub"),
                   "4": ("pick_med_entry", "pick")}
            if inp == "5":
                self.c.end = "Thank you for using StockOut Alert."
            elif inp in nxt:
                self.c.state = {"flow": nxt[inp][1]}
                self.go(nxt[inp][0])
            else:
                self.c.error = "Invalid choice."
            return

        if sc.endswith("_med_entry"):
            if inp == "0":
                return self.home()
            if len(inp) < 2 or len(inp) > 40:
                self.c.error = "Enter at least 2 letters."
                return
            meds = self.medicines(inp)
            prefix = sc.split("_")[0]
            if not meds:
                self.c.error = f"No match for '{_cut(inp, 15)}'."
                return
            if len(meds) == 1:
                self.c.state["med"] = meds[0][0]
                return self._after_medicine(prefix, is_last)
            self.go(f"{prefix}_med_select", q=inp)
            return

        if sc == "alerts_menu":
            if inp == "1":
                self.go("sub_med_entry")
            elif inp == "2":
                self._my_alerts()
            elif inp == "3":
                self._stop_all(is_last)
            elif inp == "0":
                self.home()
            else:
                self.c.error = "Invalid choice."
            return

        if sc == "find_detail":
            if inp == "1":
                self._sms_summary(is_last)
            elif inp == "0":
                self.home()
            else:
                self.c.error = "Invalid choice."
            return

        if sc in ("rep_confirm", "sub_confirm", "pick_confirm"):
            if inp == "1":
                if sc == "rep_confirm":
                    self._submit_report(is_last)
                elif sc == "sub_confirm":
                    self._subscribe(is_last)
                else:
                    self._save_pickup(is_last)
            elif inp == "2":
                self.c.end = "Cancelled. Nothing was submitted."
            elif inp == "0":
                self.home()
            else:
                self.c.error = "Invalid choice."
            return

        if sc == "pick_when":
            days = {"1": 1, "2": 3, "3": 7, "4": 14}
            if inp == "0":
                return self.home()
            if inp not in days:
                self.c.error = "Invalid choice."
                return
            s["pickup_in"] = days[inp]
            self.go("pick_interval", pickup_in=days[inp], med=s.get("med"), county=s.get("county"), flow="pick")
            return

        if sc == "pick_interval":
            iv = {"1": 14, "2": 28, "3": 30}
            if inp == "0":
                return self.home()
            if inp not in iv:
                self.c.error = "Invalid choice."
                return
            s["interval"] = iv[inp]
            self.go("pick_confirm", interval=iv[inp], pickup_in=s.get("pickup_in"), med=s.get("med"),
                    county=s.get("county"), flow="pick")
            return

        # generic paginated lists
        items = self.list_items()
        page = s.get("page", 0)
        if inp == "0":
            return self.home()
        if inp == "9" and (page + 1) * PAGE < len(items):
            s["page"] = page + 1
            return
        if not inp.isdigit() or not (1 <= int(inp) <= min(PAGE, len(items) - page * PAGE)):
            self.c.error = "Invalid choice."
            return
        chosen = items[page * PAGE + int(inp) - 1][0]
        prefix = sc.split("_")[0]
        if sc.endswith("_county"):
            s["county"] = chosen
            if sc == "find_county":
                self.go("find_med_entry")
            elif sc == "rep_county":
                self.go("rep_facility")
            elif sc == "pick_county":
                self.go("pick_when")
            else:
                self.go("sub_confirm")
        elif sc.endswith("_med_select"):
            s["med"] = chosen
            self._after_medicine(prefix, is_last)
        elif sc == "rep_facility":
            s["facility"] = chosen
            self.go("rep_confirm")
        elif sc == "find_results":
            s["facility"] = chosen
            self.go("find_detail")

    def _after_medicine(self, prefix: str, is_last: bool) -> None:
        if prefix == "find":
            self.go("find_results")
            if is_last:
                self._log_search()
        elif prefix == "rep":
            self.go("rep_county")
        elif prefix == "pick":
            self.go("pick_county")
        else:
            self.go("sub_county")

    # ------------------------------------------------------------------ side effects
    def _log_search(self) -> None:
        res = self.results()
        self.db.add(SearchRequest(medicine_id=self.c.state["med"], county_id=self.c.state["county"], channel="ussd",
                                  result_count=len(res),
                                  available_count=sum(r["status"] in ("available", "low") for r in res)))

    def _detail_result(self) -> dict | None:
        return next((r for r in self.results() if r["facility"]["id"] == self.c.state.get("facility")), None)

    def _sms_summary(self, is_last: bool) -> None:
        r = self._detail_result()
        phone = normalize_ke_phone(self.c.phone) or self.c.phone
        if r is None:
            self.c.end = "Sorry, that result is no longer available."
            return
        f, m = r["facility"], r["medicine"]
        if is_last:
            demo = "[DEMO] " if f["is_demo"] else ""
            when = r["last_updated_at"].strftime("%d %b %H:%M UTC") if r["last_updated_at"] else "no recent report"
            queue_sms(self.db, phone,
                      f"StockOut Alert {demo}{m['generic_name']} {m['strength']} at {f['name']}, {f['town'] or ''} "
                      f"{f['county']['name']}: {r['status_label']} (updated {when}). Tel {f['phone'] or 'n/a'}. "
                      "Stock may change. Call before travelling.",
                      purpose="search_result", dedupe_key=f"ussd:{self.c.session_id}:sms:{f['id']}:{m['id']}",
                      facility_id=f["id"], is_demo=f["is_demo"])
        self.c.end = "SMS summary requested. " + ("(Simulated SMS, demo)" if self.c.simulated or
                                                    not get_settings().at_configured else "It will arrive shortly.")

    def _submit_report(self, is_last: bool) -> None:
        f = self.db.get(Facility, self.c.state["facility"])
        m = self.db.get(Medicine, self.c.state["med"])
        report, _ = create_stock_report(self.db, f, m, ReportedStatus.OUT_OF_STOCK, "ussd",
                                        reporter_hash=hash_identifier(self.c.phone),
                                        dedupe_key=f"ussd:{self.c.session_id}") if is_last else (None, False)
        ref = report.reference if report else "pending"
        self.c.end = f"Report received. Ref {ref}. The facility will be asked to confirm. Thank you."

    def _subscribe(self, is_last: bool) -> None:
        phone = normalize_ke_phone(self.c.phone)
        if not phone:
            self.c.end = "Alerts are only available for Kenyan mobile numbers."
            return
        med, county = self.c.state["med"], self.c.state["county"]
        if is_last:
            sub = self.db.query(NotificationSubscription).filter_by(phone=phone, medicine_id=med,
                                                                    county_id=county).one_or_none()
            if sub is None:
                self.db.add(NotificationSubscription(phone=phone, medicine_id=med, county_id=county,
                                                     consent_source="ussd"))
            elif not sub.is_active:
                sub.is_active, sub.unsubscribed_at, sub.consent_at, sub.consent_source = True, None, utcnow(), "ussd"
        self.c.end = "Alert set. We will SMS you when it is reported available. Reply STOP to any alert to opt out."

    def _my_alerts(self) -> None:
        phone = normalize_ke_phone(self.c.phone)
        subs = (self.db.query(NotificationSubscription)
                .filter_by(phone=phone, is_active=True).limit(5).all()) if phone else []
        if not subs:
            self.c.end = "You have no active availability alerts."
            return
        lines = [f"{_cut(s.medicine.generic_name, 18)}, {s.county.name}" for s in subs]
        self.c.end = "Your alerts:\n" + "\n".join(lines)

    def _stop_all(self, is_last: bool) -> None:
        phone = normalize_ke_phone(self.c.phone)
        if phone and is_last:
            for s in self.db.query(NotificationSubscription).filter_by(phone=phone, is_active=True):
                s.is_active, s.unsubscribed_at = False, utcnow()
            for s in self.db.query(PickupSchedule).filter_by(phone=phone, is_active=True):
                s.is_active, s.unsubscribed_at = False, utcnow()
        self.c.end = "All availability alerts stopped. Pickup reminders for this number were also stopped."

    def _save_pickup(self, is_last: bool) -> None:
        from datetime import timedelta
        from app.services.pickup import today_ke, upsert_schedule
        phone = normalize_ke_phone(self.c.phone)
        if not phone:
            self.c.end = "Reminders are only available for Kenyan mobile numbers."
            return
        med = self.db.get(Medicine, self.c.state["med"])
        days = int(self.c.state.get("pickup_in") or 7)
        interval = int(self.c.state.get("interval") or 30)
        if is_last:
            upsert_schedule(
                self.db, phone=phone, medicine=med, county_id=self.c.state["county"],
                next_pickup_on=today_ke() + timedelta(days=days), interval_days=interval,
                remind_days_before=min(3, interval - 1), preferred_facility=None, consent_source="ussd",
            )
        self.c.end = "Pickup reminder saved. SMS will not name the medicine. Reply STOP to opt out."

    # ------------------------------------------------------------------ rendering
    def render(self) -> str:
        if self.c.end:
            return "END " + _cut(self.c.end, MAX_LEN)
        s = self.c.state
        sc = s["screen"]
        err = (self.c.error + "\n") if self.c.error else ""
        if sc == "main":
            body = "Welcome to StockOut Alert\n1. Find medicine\n2. Report unavailable medicine\n" \
                   "3. Availability alerts\n4. Pickup reminder\n5. Exit"
        elif sc.endswith("_med_entry"):
            body = "Enter medicine name (e.g. amoxicillin)\n0. Home"
        elif sc == "alerts_menu":
            body = "Availability alerts\n1. Subscribe\n2. My alerts\n3. Stop all alerts\n0. Home"
        elif sc == "find_detail":
            r = self._detail_result()
            if r is None:
                return "END Sorry, that result is no longer available."
            f = r["facility"]
            when = r["last_updated_at"].strftime("%d%b %H:%M") if r["last_updated_at"] else "never"
            body = (f"{_cut(f['name'], 28)}\n{r['status_label'].split(':')[0]}\nUpdated {when} UTC\n"
                    f"Tel {f['phone'] or 'n/a'}\nCall before travelling.\n1. SMS me this\n0. Home")
        elif sc == "rep_confirm":
            f, m = self.db.get(Facility, s["facility"]), self.db.get(Medicine, s["med"])
            body = f"Report {_cut(m.generic_name, 20)} unavailable at {_cut(f.name, 26)}?\n1. Confirm\n2. Cancel"
        elif sc == "sub_confirm":
            m, c = self.db.get(Medicine, s["med"]), self.db.get(County, s["county"])
            body = (f"SMS me when {_cut(m.generic_name, 20)} is reported available in {c.name}. "
                    "Reply STOP to opt out.\n1. I agree\n2. Cancel")
        elif sc == "pick_when":
            body = "Next collection?\n1. Tomorrow\n2. In 3 days\n3. In 7 days\n4. In 14 days\n0. Home"
        elif sc == "pick_interval":
            body = "How often do you collect?\n1. Every 14 days\n2. Every 28 days\n3. Every 30 days\n0. Home"
        elif sc == "pick_confirm":
            c = self.db.get(County, s["county"])
            body = (f"Remind 3 days before pickup in {c.name}. SMS will not name the medicine. "
                    "Reply STOP to opt out.\n1. I agree\n2. Cancel")
        else:
            items = self.list_items()
            titles = {"find_county": "Select county", "rep_county": "Select county", "sub_county": "Select county",
                      "pick_county": "Select county",
                      "find_med_select": "Select medicine", "rep_med_select": "Select medicine",
                      "sub_med_select": "Select medicine", "pick_med_select": "Select medicine",
                      "rep_facility": "Select facility",
                      "find_results": "Results (call first)"}
            if not items:
                return "END " + ("No participating facilities found for this area yet."
                                 if sc in ("find_results", "rep_facility") else "Nothing to show.")
            page = s.get("page", 0)
            chunk = items[page * PAGE:(page + 1) * PAGE]
            lines = [f"{i + 1}. {_cut(label, 34)}" for i, (_, label) in enumerate(chunk)]
            if (page + 1) * PAGE < len(items):
                lines.append("9. More")
            lines.append("0. Home")
            body = titles.get(sc, "") + "\n" + "\n".join(lines)
        return "CON " + _cut(err + body, MAX_LEN - 4)


def handle_ussd(db: Session, session_id: str, phone: str, service_code: str | None, text: str,
                simulated: bool = False) -> str:
    settings = get_settings()
    now = utcnow()
    text = (text or "").strip()
    sess = db.query(UssdSession).filter_by(session_id=session_id).one_or_none()
    if sess is not None:
        if sess.request_count and text == sess.last_text:
            return sess.last_response  # provider retry: identical answer, no side effects
        if now - sess.updated_at > timedelta(seconds=settings.ussd_session_timeout_seconds):
            sess.ended, sess.updated_at = True, now
            sess.last_text, sess.last_response = text, "END Session timed out. Please dial again."
            db.commit()
            return sess.last_response
        if sess.ended:
            return "END This session has ended. Please dial again."
    else:
        sess = UssdSession(session_id=session_id, phone_hash=hash_identifier(phone), service_code=service_code,
                           is_simulated=simulated, state={"screen": "main"})
        db.add(sess)

    inputs = text.split("*") if text else []
    if len(inputs) > 30:
        response = "END Too many steps. Please dial again."
        ctx = Ctx(db, session_id, phone, simulated)
    else:
        ctx = Ctx(db, session_id, phone, simulated)
        flow = Flow(ctx)
        try:
            for i, inp in enumerate(inputs):
                flow.handle(inp, is_last=(i == len(inputs) - 1))
                if ctx.end:
                    break
            response = flow.render()
        except Exception:  # noqa: BLE001
            log.exception("ussd flow error (session %s)", session_id[:8])
            db.rollback()
            sess = db.query(UssdSession).filter_by(session_id=session_id).one_or_none() or sess
            if sess not in db:
                db.add(sess)
            response = "END Sorry, something went wrong. Please try again later."

    sess.state = ctx.state
    sess.last_text = text[:300]
    sess.last_response = response
    sess.request_count = (sess.request_count or 0) + 1
    sess.updated_at = now
    sess.ended = response.startswith("END")
    db.commit()
    return response
