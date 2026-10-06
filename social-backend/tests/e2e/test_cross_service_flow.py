import io
import uuid

import numpy as np
import pytest
import requests
from PIL import Image

pytestmark = pytest.mark.e2e


def _make_image_bytes(seed, width=200, height=200):
    rng = np.random.default_rng(seed)
    arr = rng.integers(40, 215, (height, width, 3), dtype=np.uint8)
    grad = np.linspace(0, 255, width, dtype=np.uint8)
    arr[:, :, 0] = np.tile(grad, (height, 1))
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _register_and_login(base_url, username, password):
    requests.post(f"{base_url}/api/register", data={"username": username, "password": password}, timeout=10)
    resp = requests.post(f"{base_url}/api/login", data={"username": username, "password": password}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def test_new_content_uploads_successfully(live_services):
    social_url = live_services["social_url"]
    username = f"user_{uuid.uuid4().hex[:8]}"
    auth = _register_and_login(social_url, username, "testpassword123")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    img = _make_image_bytes(seed=100)
    resp = requests.post(
        f"{social_url}/api/posts/upload", headers=headers,
        files={"file": ("a.png", img, "image/png")}, timeout=15,
    )
    assert resp.status_code == 200, resp.text


def test_uploading_someone_elses_registered_content_is_blocked(live_services):
    registry_url = live_services["registry_url"]
    social_url = live_services["social_url"]

    owner_username = f"owner_{uuid.uuid4().hex[:8]}"
    owner_auth = _register_and_login(registry_url, owner_username, "testpassword123")
    owner_headers = {"Authorization": f"Bearer {owner_auth['access_token']}"}

    img = _make_image_bytes(seed=200)
    reg_resp = requests.post(
        f"{registry_url}/api/images/register", headers=owner_headers,
        files={"file": ("b.png", img, "image/png")}, timeout=15,
    )
    assert reg_resp.status_code == 200, reg_resp.text

    attacker_username = f"attacker_{uuid.uuid4().hex[:8]}"
    attacker_auth = _register_and_login(social_url, attacker_username, "testpassword123")
    attacker_headers = {"Authorization": f"Bearer {attacker_auth['access_token']}"}

    upload_resp = requests.post(
        f"{social_url}/api/posts/upload", headers=attacker_headers,
        files={"file": ("b.png", img, "image/png")}, timeout=15,
    )
    assert upload_resp.status_code == 403
    assert upload_resp.json()["detail"]["owner_name"] == owner_username

    # And the attacker's attempt must show up in the real owner's notifications,
    # end to end through both live services and both real databases.
    violations = requests.get(
        f"{social_url}/api/violations",
        headers={"Authorization": f"Bearer {_register_and_login(social_url, owner_username, 'testpassword123')['access_token']}"},
        timeout=10,
    )
    assert violations.status_code == 200
    assert len(violations.json()["notifications"]) == 1


def test_registering_own_previously_posted_content_is_not_blocked(live_services):
    """A user re-uploading/registering their own content must never trip the block --
    guards against a naive owner-check that compares IDs across the two independent
    user tables instead of usernames."""
    social_url = live_services["social_url"]
    registry_url = live_services["registry_url"]
    username = f"dual_{uuid.uuid4().hex[:8]}"

    _register_and_login(registry_url, username, "testpassword123")
    social_auth = _register_and_login(social_url, username, "testpassword123")

    img = _make_image_bytes(seed=300)
    registry_headers = {"Authorization": f"Bearer {_register_and_login(registry_url, username, 'testpassword123')['access_token']}"}
    reg_resp = requests.post(
        f"{registry_url}/api/images/register", headers=registry_headers,
        files={"file": ("c.png", img, "image/png")}, timeout=15,
    )
    assert reg_resp.status_code == 200

    social_headers = {"Authorization": f"Bearer {social_auth['access_token']}"}
    upload_resp = requests.post(
        f"{social_url}/api/posts/upload", headers=social_headers,
        files={"file": ("c.png", img, "image/png")}, timeout=15,
    )
    assert upload_resp.status_code == 200, upload_resp.text
