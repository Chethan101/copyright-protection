def test_blockchain_blocks_returns_empty_list_when_ganache_unreachable(client):
    """No Ganache is running in the test environment -- this must degrade to an
    empty list with 200, not an unhandled 500 (previously the only unguarded w3 call)."""
    resp = client.get("/api/blockchain/blocks")
    assert resp.status_code == 200
    assert resp.json() == {"blocks": []}


def test_dashboard_blocks_verified_is_zero_when_ganache_unreachable(client, auth_headers):
    resp = client.get("/api/dashboard", headers=auth_headers["headers"])
    assert resp.status_code == 200
    assert resp.json()["stats"]["blocks_verified"] == 0


def test_verify_watermark_blockchain_verified_false_when_no_contract_configured(client, registered_image, monkeypatch, test_image_bytes):
    """Distinct case from 'configured but unreachable': no contract loaded at all
    (e.g. missing contract_info.json in some deployment) must still fail closed."""
    import app.main as main_module
    from .conftest import INTERNAL_HEADERS

    monkeypatch.setattr(main_module, "CopyrightRegistry", None)

    resp = client.post(
        "/api/verify-watermark",
        headers=INTERNAL_HEADERS,
        files={"file": ("photo.png", test_image_bytes, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_registered"] is True
    assert body["blockchain_verified"] is False
