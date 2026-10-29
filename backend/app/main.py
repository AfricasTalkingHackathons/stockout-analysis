import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import SessionLocal, engine
from app.routers import admin, alerts, auth, inventory, notifications, pickup, public, reports, webhooks
from app.services.inventory import DomainError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("stockout")


def _run_jobs_sync() -> None:
    from app.services.alerts import run_periodic_checks
    from app.services.notifications import dispatch_due

    db = SessionLocal()
    try:
        run_periodic_checks(db)
        dispatch_due(db)
    finally:
        db.close()


async def _scheduler(interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(_run_jobs_sync)
        except Exception:  # noqa: BLE001
            log.exception("scheduled job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.demo_mode:
        log.warning("DEMO_MODE is ON: demo data and simulated SMS are clearly labelled in the UI.")
    if s.secret_key.startswith("dev-only"):
        log.warning("Using the development SECRET_KEY. Set SECRET_KEY before deploying.")
    task = asyncio.create_task(_scheduler(s.scheduler_interval_seconds)) if s.scheduler_enabled else None
    yield
    if task:
        task.cancel()


settings = get_settings()
app = FastAPI(
    title="StockOut Alert API",
    version="1.0.0",
    description="Medicine availability and stockout early-warning platform for Kenya. "
                "Availability data is self-reported by participating facilities.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})


_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict",
          422: "validation_error", 429: "rate_limited", 503: "unavailable"}


@app.exception_handler(StarletteHTTPException)
async def http_exc(_: Request, exc: StarletteHTTPException):
    return _error(exc.status_code, _CODES.get(exc.status_code, "error"), str(exc.detail))


@app.exception_handler(DomainError)
async def domain_exc(_: Request, exc: DomainError):
    return _error(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_exc(_: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
    return _error(422, "validation_error", "Some fields are invalid", details)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error")
    return _error(500, "internal_error", "Something went wrong. Please try again.")


for r in (auth, public, inventory, reports, alerts, notifications, pickup, admin, webhooks):
    app.include_router(r.router)


@app.get("/health", tags=["operations"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["operations"])
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT 1 FROM medicines LIMIT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return {"status": "ready", "database": "ok", "demo_mode": settings.demo_mode}
