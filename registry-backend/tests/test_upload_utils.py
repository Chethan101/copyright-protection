import os

import pytest
from fastapi import HTTPException

from app import upload_utils


def test_safe_join_allows_plain_filename(tmp_path):
    base = str(tmp_path)
    result = upload_utils.safe_join(base, "photo.jpg")
    assert result == os.path.join(os.path.abspath(base), "photo.jpg")


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../../../etc/passwd",
        "..\\..\\..\\Windows\\win.ini",
        "..\\..\\secrets.env",
        "/etc/passwd",
        "..",
        "",
    ],
)
def test_safe_join_rejects_traversal_attempts(tmp_path, malicious_name):
    base = str(tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        upload_utils.safe_join(base, malicious_name)
    assert exc_info.value.status_code == 400


def test_safe_join_rejects_any_embedded_separator_even_without_dotdot(tmp_path):
    """Stored/served filenames are always flat -- any separator is rejected outright,
    not silently flattened to a basename, even if it doesn't spell out "..'."""
    base = str(tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        upload_utils.safe_join(base, "sub/dir/file.jpg")
    assert exc_info.value.status_code == 400


def test_validate_extension_accepts_allowlisted():
    assert upload_utils.validate_extension("photo.JPG") == ".jpg"


def test_validate_extension_rejects_disallowed():
    with pytest.raises(HTTPException) as exc_info:
        upload_utils.validate_extension("payload.exe")
    assert exc_info.value.status_code == 400


def test_validate_extension_rejects_missing_extension():
    with pytest.raises(HTTPException):
        upload_utils.validate_extension("noextension")


def test_generate_filename_never_contains_client_input():
    name = upload_utils.generate_filename("orig", 5, ".png")
    assert name.startswith("orig_5_")
    assert name.endswith(".png")
    assert ".." not in name
