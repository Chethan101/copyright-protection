from dotenv import load_dotenv

load_dotenv()

import os

SECRET_KEY = os.getenv("SECRET_KEY", "dev-registry-secret-change-me")
ALGORITHM = "HS256"
ISSUER = "registry-backend"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 30)))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./registry.db")

GANACHE_RPC_URL = os.getenv("GANACHE_RPC_URL", "http://127.0.0.1:7545")

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal-key-change-me")

# Port 3000 is the standalone registry app; port 4000 is VibeSocial, which now embeds
# the registry under its profile tab and so calls this API straight from the browser.
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:4000,http://127.0.0.1:4000"
    ).split(",") if o.strip()
]

MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(50 * 1024 * 1024)))  # 50MB
ALLOWED_UPLOAD_EXTENSIONS = {
    e.strip().lower() for e in os.getenv(
        "ALLOWED_UPLOAD_EXTENSIONS",
        ".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.avi,.mkv"
    ).split(",") if e.strip()
}

DOWNLOAD_TOKEN_EXPIRE_SECONDS = int(os.getenv("DOWNLOAD_TOKEN_EXPIRE_SECONDS", "120"))

RATE_LIMIT_VERIFY = os.getenv("RATE_LIMIT_VERIFY", "20/minute")
RATE_LIMIT_REGISTER = os.getenv("RATE_LIMIT_REGISTER", "20/minute")
