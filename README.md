# StockOut Alert

Medicine availability and stockout early-warning platform for Kenya. Patients look up recently reported stock at participating pharmacies, clinics and hospitals (web, USSD, SMS). Facilities record inventory, receive low-stock and stockout alerts, and administrators can investigate a **Ripple Alert** — a potential local shortage signal when several independent facilities report the same medicine low or out of stock.

Availability is **self-reported**. Nothing is reserved. The product does not diagnose, prescribe, recommend substitutes, transfer stock or place procurement orders.

> **Demonstration environment.** Facilities named “(Demo)” are fictional. Their stock is synthetic. SMS is simulated unless Africa's Talking credentials are configured. This README does not claim a live deployment or a verified live SMS send.

## Contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Run locally](#run-locally)
4. [Hackathon demo script](#hackathon-demo-script)
5. [Availability categories and freshness](#availability-categories-and-freshness)
6. [Medicine and unit standardisation](#medicine-and-unit-standardisation)
7. [Africa's Talking](#africas-talking)
8. [Roles and demo accounts](#roles-and-demo-accounts)
9. [API surface](#api-surface)
10. [Tests](#tests)
11. [Security and privacy](#security-and-privacy)
12. [Deployment](#deployment)
13. [What still needs credentials or approval](#what-still-needs-credentials-or-approval)
14. [Known limitations](#known-limitations)
15. [Kenya Data Protection Act — unresolved](#kenya-data-protection-act--unresolved)
16. [Repeating treatment and pickup reminders](#repeating-treatment-and-pickup-reminders)

## What it does

| Actor | Can do |
| --- | --- |
| Patient / public | Search availability, find another facility for repeating treatment, pickup reminders (no diagnosis stored), SMS summary, report unavailability, subscribe to alerts, USSD |
| Facility staff | Record counts, receipts, dispenses and adjustments; view and acknowledge facility alerts |
| Facility admin | Staff, inventory, report verification, facility alerts, CSV export |
| System admin | Approve/reject/suspend facilities, catalog, runtime config, Ripple workflow, audit logs, demo reset, integration status |

Differentiators:

- Freshness is first-class: **available / low / out of stock / stale / unknown**, with configurable thresholds.
- Inventory movements are auditable, idempotent and version-checked.
- **Ripple Alert** clusters independent facility signals by medicine, county and time window. It is labelled a *potential local shortage signal for investigation*, not a confirmed regional shortage.
- **Pickup reminders** help people who collect the same medicine on a schedule. If their usual clinic is short, the product points to other participating facilities with a recent available report. It never tells anyone to take a lower dose.

## Architecture

```
Patient (web / USSD / SMS)
        │
        ▼
React (Vite)  ──proxy /api──►  FastAPI
                                   │
                     SQLAlchemy 2  │  SQLite (dev) / PostgreSQL (prod)
                                   │
                     Background jobs (stale / expiry / escalation / SMS retry)
                                   │
                     SMS/USSD provider
                       SimulatedProvider  (default in demo)
                       UnconfiguredProvider
                       AfricasTalkingProvider  (only when credentials are set)
```

- **Backend:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, JWT (HS256 with `jti` revocation), bcrypt.
- **Frontend:** React 19, Vite, TypeScript, Tailwind v4, react-router, react-hook-form + Zod, Recharts, Leaflet.
- **Time:** stored as UTC, displayed in Africa/Nairobi (EAT).

## Run locally

Requires Python 3.12+ and Node 20+.

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env          # Windows; on Unix: cp .env.example .env
alembic upgrade head
python -m app.seed demo
uvicorn app.main:app --port 8000 --reload
```

```bash
# Frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api`, `/health` and `/ready` to `http://127.0.0.1:8000`.

Optional seed commands:

```bash
python -m app.seed reference                         # counties, catalog, roles only
python -m app.seed reset-demo                        # wipe demo-flagged records and recreate
python -m app.seed create-admin you@example.com "Name"
# password from ADMIN_PASSWORD or a prompt
```

`reset-demo` deletes only records flagged as demo (`is_demo`) plus their related inventory, alerts, reports, memberships and demo users. Audit logs are kept. Unrelated user data is not deleted.

To replay the scripted walkthrough against a running server:

```bash
cd backend
python scripts/demo_walkthrough.py http://localhost:5173
```

## Hackathon demo script

Password for every fictional demo account: **`Demo#2026!`** (override with `DEMO_PASSWORD`).

1. Open `/search`. Search **Amoxicillin** in **Nairobi**. You should see:
   - Mwangaza / Baraka — reported available or out of stock depending on whether you have already run the walkthrough
   - Tumaini — reported **low** (60 vs threshold 100)
   - Upendo — **stale** (last update ~10 days ago) and “Not currently confirmed”
   - A purple banner: *Demonstration environment — facilities marked “(Demo)” are fictional*
   - Safety copy: self-reported, contact the facility before travelling, no substitutions
2. Sign in as `pharmacist.mwangaza@demo.stockout.example`. Dashboard → Inventory → Amoxicillin. Record a **dispense**, then a **count of 0**. A **stockout** alert opens. A second submit with a stale `expected_version` is rejected (`409 version_conflict`).
3. Open `/ussd` (or Settings → Inbound SMS). Simulate `STOCK MED001 0` from `+254700000031` (Baraka demo admin). The same inventory service records a count; the reply is **not** a delivery confirmation.
4. Sign in as `admin@demo.stockout.example`. **Ripple alerts** shows a signal for Amoxicillin in Nairobi: 3 facilities counted, score 2.5, interpretation *Potential local shortage signal for investigation. Not a confirmed regional shortage.* Evidence lists each facility, weight and whether it counted. Stale Upendo is excluded. Investigate → resolve with notes. Facility admins can see the signal; they cannot resolve it (`403`).
5. Open **Notifications**. Statuses are `simulated` (or `accepted` if a live provider accepted the request). Nothing is labelled **delivered** unless a delivery report arrived.
6. Sign in as `staff.mwangaza@demo.stockout.example`. Inventory and alerts are visible; **Audit logs**, **Medicine catalog** and **Settings** are hidden. Calling `/api/admin/audit-logs` returns `403`.
7. Open `/refill`. Choose **Tenofovir + Lamivudine + Dolutegravir** (or tap the chip) and **Nairobi**. Tumaini is **low**; Mwangaza and Baraka are **available**. Set a reminder — the confirmation SMS preview will not name the medicine. Do not skip or reduce a dose; go to another participating facility instead.
8. Settings → **Reset demo data** restores the scenario. Only demo-flagged records are removed.

## Availability categories and freshness

Public search never shows a facility as “in stock” on the basis of an old number. Status is computed from facility inventory **and** public reports:

| Category | Meaning |
| --- | --- |
| Reported available | Fresh report or inventory above the minimum threshold |
| Reported low stock | Fresh inventory at or below the minimum, or a fresh “low” report |
| Reported out of stock | Quantity 0, or a fresh “out of stock” report |
| Stale — needs confirmation | Last report older than `fresh_hours` (default **72**) |
| Unknown — no recent report | Last report older than `unknown_after_days` (default **30**), or never reported |

A newer confirmed “available” report supersedes older shortage signals. Unverified public reports are down-weighted; rejected reports are ignored. Quantity is shown publicly only when the facility opts in (`public_show_quantity`). Demo facilities have **no public phone number**.

Thresholds are stored in `system_config` and editable under Settings (permission `config.manage`):

| Key | Default | Role |
| --- | --- | --- |
| `fresh_hours` | 72 | When a report becomes stale |
| `unknown_after_days` | 30 | When a stale report becomes unknown |
| `early_warning_days` | 7 | Days-remaining estimate that opens an early-warning alert |
| `consumption_window_days` | 30 | Window for average daily consumption |
| `min_consumption_history_days` / `min_consumption_events` | 7 / 3 | Minimum history before an estimate is shown |
| `expiry_warning_days` | 60 | Expiring-batch alert |
| `ripple_window_hours` | 72 | Clustering window |
| `ripple_min_facilities` / `ripple_min_score` | 3 / 2.0 | Fire threshold |
| `ripple_unverified_weight` / `ripple_low_stock_weight` | 0.3 / 0.5 | Scoring |
| `alert_notify_cooldown_minutes` | 240 | Staff SMS cooldown per alert |
| `escalation_after_hours` | 12 | Unacknowledged alerts escalate |
| `subscriber_cooldown_hours` | 24 | Public availability-alert cooldown |

Ripple scoring (per medicine × county × window):

- out of stock = 1.0; low = `ripple_low_stock_weight`
- unverified × `ripple_unverified_weight`; rejected excluded; stale excluded
- a newer confirmed available zeroes older shortage signals
- each facility counts once (its maximum weight)
- fires when facilities ≥ `ripple_min_facilities` **and** score ≥ `ripple_min_score`

## Medicine and unit standardisation

The catalog is identified by **generic name + strength + dosage form + base unit**, with a stable code (`MED001` …). Brand names are search aliases only and are not used as the unit of stock.

Movements must use the medicine’s **base unit**. A count of `12` for `MED001` means 12 capsules, not 12 packs. SMS command:

```
STOCK MED001 12
STOCK FAC-D003 MED001 12    # when the sender belongs to more than one facility
STOP
HELP
```

The sender’s number must match an active membership with `can_update_stock` at an approved facility. Each Africa's Talking `messageId` is processed once.

## Africa's Talking

Three providers share one interface. The rest of the app never talks to AT directly.

| Mode | When | What happens |
| --- | --- | --- |
| `simulated` | Demo, `SMS_FORCE_SIMULATION=true`, or recipient not on `DEMO_SMS_ALLOWLIST` while demo is on | Message stored as `simulated`. **Not sent.** |
| `unconfigured` | No `AT_USERNAME` / `AT_API_KEY` and not simulated | Message stays `queued` / fails as unconfigured |
| `live-sandbox` / `live-live` | Credentials set and recipient allowed | HTTP POST to `https://api.sandbox.africastalking.com/version1/messaging` or the live host |

AT status `100` / `101` / `102` → **accepted** (the provider took the request). `500` / `501` / `502` are retried with exponential backoff (`SMS_MAX_ATTEMPTS`, `SMS_RETRY_BASE_SECONDS`). **`delivered` is set only from a delivery-report callback.** The UI never presents `simulated` or `accepted` as delivered.

### Callback URLs

Point the AT dashboard (sandbox or live) at your public API origin:

```
https://<API_HOST>/api/webhooks/ussd?token=<AT_WEBHOOK_TOKEN>
https://<API_HOST>/api/webhooks/sms?token=<AT_WEBHOOK_TOKEN>
https://<API_HOST>/api/webhooks/delivery-report?token=<AT_WEBHOOK_TOKEN>
```

Webhook security (Africa's Talking does not sign callbacks):

1. `?token=` compared with `hmac.compare_digest` against `AT_WEBHOOK_TOKEN`
2. Optional source IP allowlist `AT_WEBHOOK_ALLOWED_IPS`
3. Strict field validation; inbound SMS and USSD are idempotent on provider ids / session text

Without `AT_WEBHOOK_TOKEN`, callbacks are accepted **only in demo mode**; otherwise the server returns `503`.

USSD: every request replays the full `*`-joined text path. Side effects run only on the last input and are deduplicated per session. A repeated request with the same text returns the stored `last_response`. Sessions expire after `USSD_SESSION_TIMEOUT_SECONDS` (180). Responses start with `CON`/`END` and are capped at 182 characters.

Demo simulators (same business logic, no AT network):

- `POST /api/simulator/ussd` — public in demo mode (used by `/ussd`)
- `POST /api/simulator/sms` — requires `demo.reset` (system admin)

In demo mode, live SMS is sent only to numbers listed in `DEMO_SMS_ALLOWLIST`. Everyone else is simulated.

## Roles and demo accounts

Permissions are enforced on the **backend**. The UI hides links; it is not the access control.

| Role | Typical permissions |
| --- | --- |
| Public / patient | Search, report, subscribe, USSD. No login. |
| `facility_staff` | `inventory.view`, `inventory.update`, `alerts.view`, `alerts.manage` (own facilities) |
| `facility_admin` | Staff, facility profile, report verify, inventory export, facility alerts |
| `system_admin` | Approvals, catalog, config, ripple resolve, audit, demo reset, all facilities |

Access to another facility returns **404** (existence is not leaked).

Fictional demo users (`@demo.stockout.example`), password `Demo#2026!`:

| Email | Role | Facility |
| --- | --- | --- |
| `admin@…` | System admin | — |
| `pharmacist.mwangaza@…` | Facility admin | FAC-D001 Mwangaza Community Pharmacy (Demo) |
| `staff.mwangaza@…` | Facility staff | FAC-D001 |
| `admin.tumaini@…` | Facility admin | FAC-D002 Tumaini Health Centre (Demo) — Amoxicillin low |
| `admin.baraka@…` | Facility admin | FAC-D003 Baraka Medical Clinic (Demo) |
| `admin.upendo@…` | Facility admin | FAC-D004 Upendo Chemist (Demo) — stale (~10 days) |
| `admin.jamii@…` | Facility admin | FAC-D005 Jamii Dispensary (Demo), Kiambu |
| `admin.neema@…` | Facility admin | FAC-D006 Neema Pharmacy (Demo) — **pending**, not public |

Staff SMS numbers are fictional (`+2547000000X1`). Demo facilities have no public phone.

## API surface

Errors: `{ "error": { "code", "message", "details" } }`. Dates are ISO-8601 UTC.

Public: `GET /api/public/meta`, `/api/medicines`, `/api/locations/counties`, `/api/locations`, `/api/facilities`, `POST /api/facilities/register`, `GET /api/availability/search`, `POST /api/availability/sms-summary`.

Auth: `POST /api/auth/login`, `/logout`, `GET /api/auth/me`.

Inventory: `GET/POST /api/inventory`, `GET /api/inventory/export.csv`, `GET /api/inventory/movements`, `GET/PATCH /api/inventory/{id}`, `POST /api/inventory/{id}/movements`, `GET /api/inventory/{id}/history`.

Reports: `POST/GET /api/reports/stockout`, `GET /api/reports/lookup/{ref}`, `POST /api/reports/{id}/verify`.

Alerts: `GET /api/alerts`, `GET /api/alerts/{id}`, `POST …/acknowledge|investigate|resolve|assign`. Ripple investigate/resolve requires `ripple.manage`.

Notifications: `POST /api/notifications/test`, `GET /history`, `POST /subscriptions`, `POST /unsubscribe`, `GET /subscriptions`. Unsubscribe returns the same body whether or not the number had subscriptions.

Admin / manage: dashboard overview, audit logs, freshness, facilities (list/get/patch, approve/suspend/reject), staff, medicines, config, integrations, `POST /api/admin/jobs/run`, `POST /api/admin/ripple/scan`, `POST /api/admin/demo/reset`, users.

Webhooks and simulators as in [Africa's Talking](#africas-talking). Ops: `GET /health`, `GET /ready`.

OpenAPI: http://127.0.0.1:8000/docs when the API is running.

## Tests

```bash
cd backend
python -m pytest -q          # 91 passed (verified on this machine)

cd ../frontend
npm test                     # includes availability, auth, refill safety copy
npm run typecheck
npm run lint                 # advisory React-compiler warnings only
npm run build                # tsc -b && vite build — succeeded
```

Coverage includes availability categories, freshness, inventory idempotency and version conflicts, stockout / low / early-warning / auto-resolve, ripple weighting and workflow, USSD session replay, SMS commands, notification statuses, RBAC and demo reset.

## Security and privacy

- JWT access tokens with `jti` revocation on logout.
- Passwords hashed with bcrypt (`BCRYPT_ROUNDS`, default 12). Production refuses the development `SECRET_KEY`.
- CORS allowlist. Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- In-memory sliding-window rate limits on public and sensitive endpoints (per process — see limitations).
- Phone numbers stored hashed (`hash_identifier`) for lookups; API responses are masked (`+254******011`).
- USSD sessions store a keyed hash of the phone, not the raw number, after normalisation.
- Notification copy does not include diagnoses, prescriptions or other sensitive health information. Demo facilities prefix SMS with `[DEMO]`.
- No automatic stock transfers or procurement orders.
- `.env` is gitignored. `.env.example` contains placeholders only.

## Deployment

Files are provided; **this project has not been deployed**.

- Backend: `backend/Dockerfile` + `backend/start.sh` (`alembic upgrade head`, seed reference, optional demo seed, uvicorn).
- `render.yaml` — Render web service + PostgreSQL blueprint. `SECRET_KEY` and `AT_WEBHOOK_TOKEN` are generated; remaining AT values must be filled in the dashboard.
- Frontend: `frontend/vercel.json` — SPA rewrite to `index.html`. Set `VITE_API_URL` to the API origin at build time and add that origin to `CORS_ORIGINS`.

Production checklist:

1. `ENVIRONMENT=production` and a long random `SECRET_KEY`
2. PostgreSQL `DATABASE_URL` (a `postgres://` URL is rewritten to `postgresql://`)
3. `DEMO_MODE=false` unless you intentionally want fictional data
4. `CORS_ORIGINS` = the real frontend origin
5. Africa's Talking credentials, approved sender ID, USSD code, webhook token (see below)

## What still needs credentials or approval

These are **not** configured in this repository and have **not** been verified live:

| Item | Why |
| --- | --- |
| Africa's Talking username + API key | Sandbox or live account |
| Approved alphanumeric sender ID or short code | AT / Safaricom approval |
| USSD service code | AT application + operator approval |
| Public HTTPS origin for callbacks | So AT can reach `/api/webhooks/*` |
| `AT_WEBHOOK_TOKEN` and optional IP allowlist | Callback authenticity |
| Production `SECRET_KEY` and PostgreSQL | Hosting |
| A real test handset on `DEMO_SMS_ALLOWLIST` | Only then can a sandbox SMS be attempted |

Until those exist, every SMS in this environment is **simulated**. No live send, delivery report or USSD session from the AT network has been executed here.

## Known limitations

- Rate limiter is in-process memory. Multiple workers or a restart reset it. Use a shared store before any public launch.
- Development default is SQLite. Concurrent writes under load belong on PostgreSQL.
- Background jobs run in the API process (`SCHEDULER_INTERVAL_SECONDS`). A dedicated worker is safer in production.
- Map tiles come from the public OSM tile servers (fine for a demo; not a production SLA).
- Leaflet is lazy-loaded; first map view needs a network connection for CSS/tiles.
- Frontend lint reports React-compiler *warnings* (setState-in-effect, `only-export-components`). They are not build failures.
- The product does not integrate DHIS2, KEMSA, or any government system, and does not claim to.

## Kenya Data Protection Act — unresolved

StockOut Alert is designed to minimise personal data (no diagnoses, masked phones, hashed identifiers, explicit SMS consent, identical unsubscribe responses). The following are **not done** and would be required before any real-world processing of Kenyan personal data:

- Registration with the Office of the Data Protection Commissioner (if the organisation is a data controller/processor that must register)
- A published privacy notice naming the controller, purposes, retention and rights
- A lawful basis assessment for each processing activity (consent is used for availability SMS; staff accounts need a separate basis)
- Data processing agreements with Africa's Talking and the hosting provider
- Documented retention and deletion schedules (inbound SMS, USSD sessions, audit logs, notification history)
- A process for access, correction and erasure requests
- Cross-border transfer assessment if the database or AT processing is outside Kenya
- Incident-response and breach-notification procedure (72-hour ODPC notification)
- DPIA if the live service is likely to be high-risk (health-adjacent, large scale)

Until those are in place, run only the fictional demo dataset.

## Repeating treatment and pickup reminders

People on a regular collection schedule (including long-term treatments) can use **`/refill`** or USSD option **4. Pickup reminder**.

What it does:

1. Shows participating facilities with a **recent available or low-stock report** for the medicine they collect.
2. If the usual clinic is low or out, lists other participating facilities in the same county (the demo uses Tumaini low / out, with Mwangaza and Baraka still reporting stock).
3. Sends an SMS a few days before the next collection date, then repeats on the chosen interval (14 / 28 / 30 / 60 / 90 days).
4. Shows facility teams an **aggregated** “upcoming collections” count (no names, no phone numbers) so they can see demand against last reported quantity. Stock is never transferred automatically.

What it will not do:

- Store a diagnosis (no HIV, TB or other condition field)
- Name the medicine in reminder SMS
- Tell anyone to skip, split or reduce a dose
- Reserve stock or create a clinic appointment
- Move medicine between facilities

`STOP` and `/unsubscribe` end both availability alerts and pickup reminders. The response is the same whether or not the number had any.

Demo seed includes a fictional reminder (`+254700000088`, TLD at Tumaini) due inside the reminder window so Settings → Run jobs will queue a **simulated** SMS.

## Frontend pages

Public: `/` landing, `/search`, `/refill`, `/facilities/:id`, `/login`, `/register`, `/ussd`, `/unsubscribe`, `/report`.

App (permission-gated): `/app` dashboard, inventory, inventory detail, movements, alerts, ripple, reports, facilities, catalog, notifications, audit, settings.
