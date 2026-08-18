from dotenv import load_dotenv

load_dotenv()

import os

SECRET_KEY = os.getenv("SECRET_KEY", "dev-social-secret-change-me")
ALGORITHM = "HS256"
ISSUER = "social-backend"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./social.db")

REGISTRY_URL = os.getenv("REGISTRY_URL", "http://127.0.0.1:8000/api")
# Verification scans the whole registry, so the ceiling has to allow for a large corpus
# and long/high-resolution uploads. Typical checks finish in about a second.
REGISTRY_TIMEOUT_SECONDS = float(os.getenv("REGISTRY_TIMEOUT_SECONDS", "45"))
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal-key-change-me")

CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:4000,http://127.0.0.1:4000"
    ).split(",") if o.strip()
]

MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(50 * 1024 * 1024)))  # 50MB
ALLOWED_UPLOAD_EXTENSIONS = {
    e.strip().lower() for e in os.getenv(
        "ALLOWED_UPLOAD_EXTENSIONS",
        ".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.avi,.mkv"
    ).split(",") if e.strip()
}

RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "20/minute")
