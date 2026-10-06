import os
import uuid
from fastapi import HTTPException, UploadFile
from . import config


def validate_extension(filename: str) -> str:
    """Check the client-supplied filename's extension against the allowlist.
    Returns the (lowercased) extension. Raises 400 if missing/disallowed."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in config.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")
    return ext


def generate_filename(prefix: str, owner_id, ext: str) -> str:
    """Build an on-disk filename with no client-controlled characters in it."""
    return f"{prefix}_{owner_id}_{uuid.uuid4().hex}{ext}"


async def save_upload_streaming(file: UploadFile, dest_path: str, max_bytes: int = None) -> int:
    """Stream an UploadFile to dest_path in chunks, enforcing a max size.
    Deletes the partial file and raises 413/400 rather than leaving orphaned bytes on disk."""
    max_bytes = max_bytes if max_bytes is not None else config.MAX_UPLOAD_SIZE_BYTES
    chunk_size = 1024 * 1024
    total = 0
    try:
        with open(dest_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="File too large")
                buffer.write(chunk)
    except Exception:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise
    finally:
        await file.close()

    if total == 0:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=400, detail="Empty file")
    return total


MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
}


def media_type_for(path: str) -> str:
    """Content-Type for a stored file. Serving a .webm or .png under the wrong type
    makes browsers refuse to render it, so map each extension explicitly."""
    return MEDIA_TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def safe_join(base_dir: str, name: str) -> str:
    """Resolve `name` under `base_dir`. Stored/served filenames here are always flat
    (no subdirectories), so ANY path separator (forward OR back slash, regardless of
    host OS) or ".." component is rejected outright rather than silently stripped --
    explicit rejection is easier to audit than relying on os.path.basename's
    OS-dependent separator handling to neutralize traversal attempts quietly."""
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    normalized = name.replace("\\", "/")
    if "/" in normalized or normalized in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    base_dir_abs = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base_dir_abs, normalized))
    if os.path.commonpath([candidate, base_dir_abs]) != base_dir_abs:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return candidate
