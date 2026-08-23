from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from .database import engine, Base
from . import models, auth, watermark_engine, upload_utils, config
import json, logging, os, uuid
from datetime import datetime
from web3 import Web3

logger = logging.getLogger("registry.blockchain")

Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

w3 = Web3(Web3.HTTPProvider(config.GANACHE_RPC_URL))


def _ensure_default_account():
    """
    Resolve w3.eth.default_account on demand rather than once at import time.

    A one-shot attempt at startup is fragile: if Ganache isn't reachable yet at that
    exact moment (a startup ordering race, or the node still booting), the account stays
    unset for the rest of the process's life and every subsequent transact() silently
    fails -- even after Ganache comes up seconds later. Re-checking here means the very
    next registration after Ganache becomes reachable just works, with no restart needed.

    web3.py represents "unset" as its own `Empty` sentinel, not None or a falsy value --
    `w3.eth.default_account is not None` is therefore always true and never re-attempts
    the assignment. An address is a plain str at runtime (ChecksumAddress is only a
    NewType, not a real class, so isinstance against it is not usable here) -- confirmed
    via a live Web3RPCError where an unset default_account was passed straight through
    to a transaction's `from` field as that sentinel object instead of an address.
    """
    if isinstance(w3.eth.default_account, str):
        return True
    try:
        w3.eth.default_account = w3.eth.accounts[0]
        return True
    except Exception:
        return False


_ensure_default_account()
contract_info_path = os.path.join(os.path.dirname(__file__), 'contract_info.json')
CopyrightRegistry = None
if os.path.exists(contract_info_path):
    try:
        with open(contract_info_path, 'r') as f:
            contract_data = json.load(f)
            CopyrightRegistry = w3.eth.contract(address=contract_data['address'], abi=contract_data['abi'])
    except Exception:
        pass

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
WATERMARKED_DIR = os.path.join(os.path.dirname(__file__), 'watermarked')
ORIGINAL_DIR = os.path.join(os.path.dirname(__file__), 'originals')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(WATERMARKED_DIR, exist_ok=True)
os.makedirs(ORIGINAL_DIR, exist_ok=True)

INTERNAL_API_KEY = config.INTERNAL_API_KEY

# A visual match this strong will not be beaten by a later candidate, so the scan can
# stop rather than running ORB against the rest of the registry.
ORB_CONFIDENT_ENOUGH = 97.0


class _Lazy:
    """Defer an expensive computation until (and unless) it is actually needed."""

    __slots__ = ("_factory", "_value", "_done")

    def __init__(self, factory):
        self._factory = factory
        self._value = None
        self._done = False

    @property
    def value(self):
        if not self._done:
            self._value = self._factory()
            self._done = True
        return self._value


@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...), db: Session = Depends(auth.get_db)):
    auth.validate_credentials(username, password)
    username = username.strip()
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    user = models.User(username=username, password_hash=auth.get_password_hash(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username already registered")
    return {"msg": "Registered successfully"}

@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(auth.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect credentials")
    access_token = auth.create_access_token(data={"sub": user.username, "user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/images/register")
@limiter.limit(config.RATE_LIMIT_REGISTER)
async def register_image(request: Request, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    ext = upload_utils.validate_extension(file.filename)
    original_filename = upload_utils.generate_filename("orig", current_user.id, ext)
    original_path = os.path.join(ORIGINAL_DIR, original_filename)
    await upload_utils.save_upload_streaming(file, original_path, config.MAX_UPLOAD_SIZE_BYTES)

    try:
        is_video = watermark_engine.is_video_file(original_path)
        if is_video:
            image_hash = watermark_engine.get_video_perceptual_hash(original_path)
        else:
            image_hash = watermark_engine.get_perceptual_hash(original_path)
    except Exception:
        os.remove(original_path)
        raise HTTPException(status_code=400, detail="Unsupported or corrupt file")

    # Check if already registered in DB first
    existing = db.query(models.ImageRecord).filter(models.ImageRecord.image_hash == image_hash).first()
    if existing:
        os.remove(original_path)
        raise HTTPException(status_code=400, detail="Image or video already registered")

    # Generate watermark_id FIRST so it's consistent in both DB and blockchain
    watermark_id = str(uuid.uuid4())[:8]
    watermark_bits = watermark_engine.str_to_binary(watermark_id)
    # The watermarked copy is what owners download and re-share, so it must be playable
    # in a browser. Containers like .avi/.mkv never are -- always hand back MP4/H.264.
    output_ext = watermark_engine.BROWSER_PLAYABLE_VIDEO_EXT if is_video else ext
    output_filename = upload_utils.generate_filename("wm", current_user.id, output_ext)
    output_path = os.path.join(WATERMARKED_DIR, output_filename)

    try:
        if is_video:
            watermark_engine.embed_video_watermark(original_path, watermark_bits, output_path)
        else:
            watermark_engine.embed_watermark(original_path, watermark_bits, output_path)
    except Exception:
        if os.path.exists(original_path):
            os.remove(original_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(status_code=400, detail="Unsupported or corrupt file")

    # Try blockchain registration with correct watermark_id
    tx_hash_hex = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}"
    block_number = 0
    blockchain_registered = False
    if CopyrightRegistry and _ensure_default_account():
        try:
            owner_id, wm_id, ts, is_reg = CopyrightRegistry.functions.verifyImage(image_hash).call()
            if is_reg:
                os.remove(original_path)
                os.remove(output_path)
                raise HTTPException(status_code=400, detail="Image already registered on blockchain")
            # Pass `from` explicitly rather than relying on w3.eth.default_account being
            # picked up implicitly -- confirmed this web3.py/Ganache combination rejects
            # the transaction ("from not found; is required") without it, even though
            # default_account is set.
            tx_hash = CopyrightRegistry.functions.registerImage(image_hash, str(current_user.id), watermark_id).transact({"from": w3.eth.default_account})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            tx_hash_hex = tx_hash.hex()
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            block_number = receipt.blockNumber
            blockchain_registered = True
        except HTTPException:
            raise
        except Exception:
            # Blockchain unavailable -- continue with DB-only registration, but log it
            # rather than failing silently. A silent swallow here is exactly what let a
            # real, persistent chain-connectivity fault go unnoticed for a long time.
            logger.exception("Blockchain registration failed for image_hash=%s; falling back to DB-only", image_hash)

    img_record = models.ImageRecord(owner_id=current_user.id, image_hash=image_hash, watermark_id=watermark_id, tx_hash=tx_hash_hex, watermarked_path=output_filename, original_path=original_filename)
    db.add(img_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if os.path.exists(original_path):
            os.remove(original_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(status_code=400, detail="Image or video already registered")
    db.refresh(img_record)

    return {
        "msg": "Transaction Successful" if blockchain_registered else "Registered successfully (blockchain notarization unavailable, recorded in registry only)",
        "image_id": img_record.id,
        "image_hash": image_hash,
        "tx_hash": tx_hash_hex,
        "owner_id": current_user.id,
        "watermark_id": watermark_id,
        "block_number": block_number,
        "blockchain_registered": blockchain_registered
    }

@app.post("/api/verify-watermark")
@limiter.limit(config.RATE_LIMIT_VERIFY)
async def verify_watermark(request: Request, file: UploadFile = File(...), x_registry_internal: str = Header(None), db: Session = Depends(auth.get_db)):
    if x_registry_internal != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    ext = upload_utils.validate_extension(file.filename)
    temp_path = os.path.join(UPLOAD_DIR, upload_utils.generate_filename("check", "anon", ext))
    await upload_utils.save_upload_streaming(file, temp_path, config.MAX_UPLOAD_SIZE_BYTES)

    matched_image = None
    confidence = 0.0
    match_method = None

    try:
        WATERMARK_BITS = 8 * 8  # 8 ASCII chars × 8 bits each
        is_video = watermark_engine.is_video_file(temp_path)

        # Step 1: Extract watermark ID
        if is_video:
            extracted_bits = watermark_engine.extract_video_watermark(temp_path, WATERMARK_BITS)
            # Videos yield more than one candidate hash so records stored under an older
            # frame convention still compare correctly (see the engine for why).
            uploaded_phash_strs = watermark_engine.get_video_perceptual_hash_candidates(temp_path)
        else:
            extracted_bits = watermark_engine.extract_watermark(temp_path, WATERMARK_BITS)
            uploaded_phash_strs = [watermark_engine.get_perceptual_hash(temp_path)]

        extracted_wid = watermark_engine.binary_to_str(extracted_bits)
        uploaded_phashes = [watermark_engine.imagehash.hex_to_hash(h) for h in uploaded_phash_strs]

        all_images = db.query(models.ImageRecord).all()

        # Describe the uploaded file once and reuse it for every candidate; this is by
        # far the most-repeated work in the scan. Computed lazily so a watermark or
        # perceptual-hash hit can settle the question without paying for it at all. For
        # video this is several frames sampled across the clip, not one keyframe -- a
        # single fixed position cannot reliably represent a whole video (see engine).
        query_orb_features = _Lazy(lambda: watermark_engine.compute_orb_features_multi(
            watermark_engine.orb_reference_paths(temp_path)))

        for img in all_images:
            # Primary: watermark_id exact match (strongest signal) -- the hidden,
            # invisible DWT-DCT watermark embedded at registration time. Survives
            # re-saves, mild recompression, and exact re-uploads of the watermarked file.
            if extracted_wid == img.watermark_id:
                matched_image = img
                confidence = 99.9
                match_method = "watermark"
                break

            # Secondary: perceptual hash similarity (phash distance <= 8 out of 256 bits).
            # Catches near-identical copies (recompression, minor resize/crop) even if
            # the watermark bits themselves didn't survive majority-vote extraction.
            try:
                db_phash = watermark_engine.imagehash.hex_to_hash(img.image_hash)
                phash_dist = min(candidate - db_phash for candidate in uploaded_phashes)
                if phash_dist <= 8:
                    phash_conf = max(60.0, 95.0 - phash_dist * 4)
                    if phash_conf > confidence:
                        matched_image = img
                        confidence = phash_conf
                        match_method = "perceptual_hash"
            except Exception:
                pass

            # Tertiary: ORB structural feature matching -- this is what catches
            # screenshots and mobile-camera re-photographs, where both the watermark and
            # the perceptual hash are destroyed by resampling, perspective distortion and
            # lighting changes, but the underlying visual structure (edges/corners) still
            # lines up under a RANSAC homography. The watermarked rendition is checked
            # first because that is the copy that actually circulates publicly; the
            # original is only consulted if that did not already settle it (the two are
            # perceptually identical by design, so the second pass rarely adds anything).
            for directory, stored_name in ((WATERMARKED_DIR, img.watermarked_path),
                                           (ORIGINAL_DIR, img.original_path)):
                if not stored_name:
                    continue
                candidate_path = upload_utils.safe_join(directory, stored_name)
                if not os.path.exists(candidate_path):
                    continue
                candidate_features = watermark_engine.compute_orb_features_multi(
                    watermark_engine.orb_reference_paths(candidate_path))
                orb_score = watermark_engine.best_orb_similarity_from_features(
                    query_orb_features.value, candidate_features)
                if orb_score > 25.0 and orb_score > confidence:
                    matched_image = img
                    confidence = orb_score
                    match_method = "orb_visual_similarity"
                if confidence >= ORB_CONFIDENT_ENOUGH:
                    break

            if confidence >= ORB_CONFIDENT_ENOUGH:
                break

    except Exception:
        matched_image = None
        confidence = 0.0
        match_method = None
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            # The upload is a one-off temp file; any ORB sample frames cached next to it
            # are useless once it's gone (unlike registered content, which is compared
            # again on future requests and benefits from keeping its cache).
            for i in range(len(watermark_engine.VIDEO_ORB_SAMPLE_POSITIONS)):
                cached = f"{temp_path}_orbkf{i}.jpg"
                if os.path.exists(cached):
                    os.remove(cached)
        except Exception:
            pass

    if matched_image and confidence > 50.0:
        owner_id = matched_image.owner_id
        watermark_id = matched_image.watermark_id
        registered_at = matched_image.timestamp.isoformat()
        owner_source = "registry"

        # The chain is the authoritative record of ownership. When it is reachable and
        # holds this hash, report the owner/watermark/timestamp it actually stores rather
        # than the local mirror -- that is the whole point of notarizing the registration.
        blockchain_verified = False
        if CopyrightRegistry:
            try:
                owner_id_bc, wm_id_bc, ts_bc, is_reg = CopyrightRegistry.functions.verifyImage(matched_image.image_hash).call()
                blockchain_verified = is_reg
                if is_reg:
                    owner_source = "blockchain"
                    if wm_id_bc:
                        watermark_id = wm_id_bc
                    if owner_id_bc:
                        try:
                            owner_id = int(owner_id_bc)
                        except (TypeError, ValueError):
                            pass
                    if ts_bc:
                        registered_at = datetime.utcfromtimestamp(int(ts_bc)).isoformat()
            except Exception:
                blockchain_verified = False

        owner_user = db.query(models.User).filter(models.User.id == owner_id).first()

        return {
            "is_registered": True,
            "watermark_id": watermark_id,
            "image_id": matched_image.id,
            "owner_id": owner_id,
            "owner_name": owner_user.username if owner_user else "Unknown",
            "owner_source": owner_source,
            "tx_hash": matched_image.tx_hash,
            "timestamp": registered_at,
            "confidence": round(confidence, 2),
            "match_method": match_method,
            "blockchain_verified": blockchain_verified
        }

    return {"is_registered": False}


@app.get("/api/dashboard")
def get_dashboard(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    images = db.query(models.ImageRecord).filter(models.ImageRecord.owner_id == current_user.id).all()
    all_images_count = db.query(models.ImageRecord).count()
    try:
        blocks_verified = w3.eth.block_number
    except Exception:
        blocks_verified = 0
    return {
        "user": {"id": current_user.id, "username": current_user.username},
        "stats": {
            "my_images": len(images),
            "total_network_images": all_images_count,
            "blocks_verified": blocks_verified
        },
        "images": [{"id": img.id, "watermark_id": img.watermark_id, "tx_hash": img.tx_hash, "timestamp": img.timestamp.isoformat(), "owner_id": img.owner_id} for img in images]
    }

@app.post("/api/images/{image_id}/download-token")
def create_download_token(image_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    img = db.query(models.ImageRecord).filter(models.ImageRecord.id == image_id, models.ImageRecord.owner_id == current_user.id).first()
    if not img:
        raise HTTPException(status_code=404, detail="File not found")
    token = auth.create_access_token(
        data={"sub": current_user.username, "user_id": current_user.id, "image_id": image_id},
        expires_minutes=config.DOWNLOAD_TOKEN_EXPIRE_SECONDS / 60,
        purpose="download"
    )
    return {"token": token, "expires_in": config.DOWNLOAD_TOKEN_EXPIRE_SECONDS}

@app.get("/api/images/{image_id}/download")
def download_image(image_id: int, token: str, db: Session = Depends(auth.get_db)):
    try:
        payload = auth.decode_token(token)
        if payload.get("purpose") != "download" or payload.get("image_id") != image_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        username = payload.get("sub")
        current_user = db.query(models.User).filter(models.User.username == username).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    img = db.query(models.ImageRecord).filter(models.ImageRecord.id == image_id, models.ImageRecord.owner_id == current_user.id).first()
    if not img or not img.watermarked_path:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = upload_utils.safe_join(WATERMARKED_DIR, img.watermarked_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(file_path, media_type=upload_utils.media_type_for(file_path),
                        filename=img.watermarked_path)

@app.get("/api/blockchain/blocks")
def get_blockchain_blocks():
    try:
        latest_block = w3.eth.block_number
        blocks = []

        start_block = max(0, latest_block - 10)
        for i in range(latest_block, start_block - 1, -1):
            block = w3.eth.get_block(i, full_transactions=True)
            txs = []
            for tx in block.transactions:
                txs.append({
                    "hash": tx.hash.hex(),
                    "from": tx['from'],
                    "to": tx['to'],
                })

            blocks.append({
                "number": block.number,
                "hash": block.hash.hex(),
                "parentHash": block.parentHash.hex(),
                "timestamp": block.timestamp,
                "transactions": txs
            })

        return {"blocks": blocks}
    except Exception:
        return {"blocks": []}
