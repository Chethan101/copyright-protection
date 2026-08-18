import contextlib
import os
import socket
import subprocess
import sys
import time

import pytest
import requests


def _free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(url, timeout=25):
    deadline = time.time() + timeout
    last_exc = None
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=1)
            if r.status_code < 500:
                return
        except Exception as e:
            last_exc = e
        time.sleep(0.3)
    raise RuntimeError(f"Service at {url} did not become ready in time: {last_exc}")


@pytest.fixture(scope="module")
def live_services(tmp_path_factory):
    """Spawns real registry-backend and social-backend processes on throwaway ports
    and throwaway SQLite files, wired together exactly like production (social's
    REGISTRY_URL pointed at the real registry instance, shared INTERNAL_API_KEY).

    In-process TestClient dual-import isn't viable here: both backends' packages are
    both literally named `app`, so importing both as top-level `app` in one process
    collides in sys.modules. Real subprocesses sidestep that entirely and, as a bonus,
    validate the actual env-var wiring (REGISTRY_URL, INTERNAL_API_KEY, DATABASE_URL)
    across a real process/network boundary instead of through mocks.
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))
    social_backend_dir = os.path.abspath(os.path.join(this_dir, "..", ".."))
    repo_root = os.path.abspath(os.path.join(social_backend_dir, ".."))
    registry_backend_dir = os.path.join(repo_root, "registry-backend")

    if os.name == "nt":
        python_exe = os.path.join(repo_root, "venv", "Scripts", "python.exe")
    else:
        python_exe = os.path.join(repo_root, "venv", "bin", "python")

    registry_port = _free_port()
    social_port = _free_port()

    tmp_dir = tmp_path_factory.mktemp("e2e")
    registry_db = tmp_dir / "registry_e2e.db"
    social_db = tmp_dir / "social_e2e.db"
    shared_internal_key = "e2e-shared-internal-key"

    registry_env = dict(os.environ)
    registry_env.update({
        "DATABASE_URL": f"sqlite:///{registry_db}",
        "SECRET_KEY": "e2e-registry-secret",
        "INTERNAL_API_KEY": shared_internal_key,
        "GANACHE_RPC_URL": "http://127.0.0.1:18999",  # deliberately unreachable; see registry conftest
        "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
    })

    social_env = dict(os.environ)
    social_env.update({
        "DATABASE_URL": f"sqlite:///{social_db}",
        "SECRET_KEY": "e2e-social-secret",
        "INTERNAL_API_KEY": shared_internal_key,
        "REGISTRY_URL": f"http://127.0.0.1:{registry_port}/api",
        "CORS_ALLOWED_ORIGINS": "http://localhost:4000",
    })

    registry_proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "app.main:app", "--port", str(registry_port)],
        cwd=registry_backend_dir, env=registry_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    social_proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "app.main:app", "--port", str(social_port)],
        cwd=social_backend_dir, env=social_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    try:
        _wait_until_ready(f"http://127.0.0.1:{registry_port}/docs")
        _wait_until_ready(f"http://127.0.0.1:{social_port}/docs")
        yield {
            "registry_url": f"http://127.0.0.1:{registry_port}",
            "social_url": f"http://127.0.0.1:{social_port}",
        }
    finally:
        for proc in (registry_proc, social_proc):
            proc.terminate()
        for proc in (registry_proc, social_proc):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
