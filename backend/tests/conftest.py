import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="stockout-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "DEMO_MODE": "true",
    "SCHEDULER_ENABLED": "false",
    "AT_USERNAME": "",
    "AT_API_KEY": "",
    "AT_WEBHOOK_TOKEN": "",
    "BCRYPT_ROUNDS": "4",
    "SECRET_KEY": "test-secret-key-for-pytest-only",
    "RATE_LIMIT_PUBLIC_PER_MINUTE": "10000",
    "RATE_LIMIT_SENSITIVE_PER_MINUTE": "10000",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402
from app.seed import DEMO_EMAIL_DOMAIN, seed_demo  # noqa: E402
from app.services.sms_providers import set_provider_override  # noqa: E402

PASSWORD = get_settings().demo_password


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    seed_demo(db)
    db.close()
    limiter.reset()
    set_provider_override(None)
    yield
    set_provider_override(None)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client, local: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{local}@{DEMO_EMAIL_DOMAIN}", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin_h(client):
    return login(client, "admin")


@pytest.fixture
def mwangaza_h(client):
    return login(client, "pharmacist.mwangaza")


@pytest.fixture
def tumaini_h(client):
    return login(client, "admin.tumaini")
