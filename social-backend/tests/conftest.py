import os

# Must happen before any `app.*` import -- see registry-backend/tests/conftest.py for
# the full rationale (module-level create_all() + config reads at import time).
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-social-secret")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
os.environ.setdefault("REGISTRY_URL", "http://127.0.0.1:18999/api")  # unreachable; mocked per-test anyway

import io
import uuid

import numpy as np
import pytest
import requests as real_requests
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app  # noqa: E402
from app.database import Base  # noqa: E402
from app import auth  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[auth.get_db] = override_get_db
    app.state.limiter.reset()

    import app.main as main_module

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main_module, "UPLOAD_DIR", str(upload_dir))

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def make_test_image_bytes(width=64, height=64, seed=0) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def test_image_bytes():
    return make_test_image_bytes(seed=1)


@pytest.fixture()
def register_user(client):
    def _register(username=None, password="testpassword123"):
        username = username or f"user_{uuid.uuid4().hex[:8]}"
        resp = client.post("/api/register", data={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        return username, password

    return _register


@pytest.fixture()
def auth_headers(client, register_user):
    username, password = register_user()
    resp = client.post("/api/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "username": username, "password": password}


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.exceptions.HTTPError(f"{self.status_code} Error")


@pytest.fixture()
def mock_registry(monkeypatch):
    """Stubs out social-backend's HTTP call to registry-backend's /verify-watermark.
    Usage: mock_registry(json_response={"is_registered": False})
           mock_registry(exception=requests.exceptions.ConnectionError("down"))
    """
    import app.main as main_module

    state = {"response": FakeResponse({"is_registered": False}), "exception": None}
    calls = []

    def fake_post(url, *args, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        if state["exception"]:
            raise state["exception"]
        return state["response"]

    monkeypatch.setattr(main_module.requests, "post", fake_post)

    def _set(json_response=None, status_code=200, exception=None):
        if exception is not None:
            state["exception"] = exception
        else:
            state["response"] = FakeResponse(json_response, status_code)
            state["exception"] = None

    _set.calls = calls
    return _set
