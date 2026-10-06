import os

# Must happen before any `app.*` import: app/main.py runs Base.metadata.create_all()
# at import time using whatever DATABASE_URL is active, and app/config.py reads
# SECRET_KEY/INTERNAL_API_KEY at import time too. Setting these first keeps a plain
# `pytest` run from ever touching the real registry.db or a production secret.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-registry-secret")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
# Point at a deliberately-unreachable port rather than leaving the real default
# (127.0.0.1:7545): a developer machine may well have an actual Ganache instance
# running there, and we must never read from or write test transactions into it.
# An unreachable Ganache is exactly the condition we want to exercise anyway
# (blockchain-optional fallback paths).
os.environ.setdefault("GANACHE_RPC_URL", "http://127.0.0.1:18999")

import io
import uuid

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app  # noqa: E402
from app.database import Base  # noqa: E402
from app import auth  # noqa: E402

INTERNAL_HEADERS = {"x-registry-internal": "test-internal-key"}


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
    # Fresh rate-limit counters per test so the shared TestClient "identity" doesn't
    # accumulate hits across unrelated tests and trip 429s.
    app.state.limiter.reset()

    # Redirect file storage to a throwaway per-test directory so running the suite
    # never writes synthetic test media into the real app/{originals,watermarked,uploads}.
    import app.main as main_module

    for attr in ("ORIGINAL_DIR", "WATERMARKED_DIR", "UPLOAD_DIR"):
        d = tmp_path / attr.lower()
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(main_module, attr, str(d))

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def make_test_image_bytes(width=256, height=256, seed=0, fmt="PNG") -> bytes:
    """Synthetic, non-solid-color image so DWT block texture actually varies
    (a flat color would keep every block at ALPHA_MIN and give the weakest signal)."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(40, 215, (height, width, 3), dtype=np.uint8)
    grad = np.linspace(0, 255, width, dtype=np.uint8)
    arr[:, :, 0] = np.tile(grad, (height, 1))
    arr[height // 4: height // 2, width // 4: width // 2, :] = 20  # a flat block too
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def make_test_video_bytes(frames=16, fps=8, width=128, height=128, seed=0):
    """Returns raw mp4 bytes, or None if the mp4v codec isn't available in this environment.
    Frames share one base scene with small per-frame jitter (like real camera sensor noise)
    rather than fully independent noise per frame -- real video has temporal coherence, and
    a "different random image every frame" stress-test defeats even legitimate cross-frame
    majority-vote extraction in a way no real video would."""
    import cv2
    import tempfile

    path = os.path.join(tempfile.gettempdir(), f"synthtest_{uuid.uuid4().hex}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    if not writer.isOpened():
        return None
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 215, (height, width, 3), dtype=np.uint8)
    grad = np.linspace(0, 255, width, dtype=np.uint8)
    base[:, :, 0] = np.tile(grad, (height, 1))
    for _ in range(frames):
        jitter = rng.integers(-3, 3, (height, width, 3))
        frame = np.clip(base.astype(np.int16) + jitter, 0, 255).astype(np.uint8)
        writer.write(frame)
    writer.release()
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, "rb") as f:
        data = f.read()
    os.remove(path)
    return data


@pytest.fixture()
def test_image_bytes():
    return make_test_image_bytes(seed=1)


@pytest.fixture()
def other_image_bytes():
    return make_test_image_bytes(seed=99)


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


@pytest.fixture()
def registered_image(client, auth_headers, test_image_bytes):
    resp = client.post(
        "/api/images/register",
        headers=auth_headers["headers"],
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
