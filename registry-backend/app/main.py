from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from .database import engine, Base
from . import models, auth, watermark_engine, upload_utils, config
import json, logging, os, uuid
from datetime import datetime, timezone
from web3 import Web3


def utc_iso(dt):
    """
    Serialize a stored timestamp as explicit UTC (e.g. ...+00:00).

    Timestamps are stored as naive UTC (datetime.utcnow). Sent without an offset, a
    browser reads them as LOCAL time -- in India every post then appeared 5h30m older
    than it was ("5h ago" for something just posted).
    """
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()

logger = logging.getLogger("registry.blockchain")

Base.metadata.create_all(bind=engine)


def _migrate_user_origin():
    """Add users.origin to databases created before it existed. Accounts that already
    exist are treated as linked to the VibeSocial account of the same name -- that is how
    they have been used so far -- so current users keep working."""
    from sqlalchemy import text
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        if cols and "origin" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN origin VARCHAR NOT NULL DEFAULT 'social'"))


_migrate_user_origin()

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



class _Lazy:
    """Defer an expensive computation until (and unless) it is actually needed."""

    __slots__ = ("_factory", "_value", "_done", "_error")

    def __init__(self, factory):
        self._factory = factory
        self._value = None
        self._done = False
        self._error = None

    @property
    def value(self):
        if self._error is not None:
            raise self._error          # failed once: don't recompute it for every record
        if not self._done:
            try:
                self._value = self._factory()
            except Exception as exc:
                self._error = exc
                raise
            self._done = True
        return self._value


class _UploadUnreadable(Exception):
    """The uploaded file itself could not be analysed -- the check must fail closed."""


@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...), db: Session = Depends(auth.get_db)):
    auth.validate_credentials(username, password)
    username = username.strip()
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    user = models.User(username=username, password_hash=auth.get_password_hash(password), origin="registry")
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

@app.post("/api/internal/session")
def internal_session(username: str = Form(...), x_registry_internal: str = Header(None),
                     db: Session = Depends(auth.get_db)):
    """
    Issue a registry session for a user another trusted service has already authenticated.

    VibeSocial embeds this registry and brokers sign-in through here so a creator does not
    keep a second account: it presents the shared internal key plus the username it has
    already authenticated, and gets back a normal registry token for that same username.

    Matching on username is what makes ownership work end to end -- the two services have
    independent id spaces, so a copyright block is attributed by username. Provisioning the
    registry account under the caller's exact username is therefore what lets a creator post
    their own registered work; a mismatch would have them blocked from their own content.

    The account is created without a usable password, so it is reachable only through this
    brokered path. Accounts created through the registry's own signup are never handed
    out here, even when the username matches.
    """
    if x_registry_internal != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if len(username) > 64:
        raise HTTPException(status_code=400, detail="Username too long")

    user = db.query(models.User).filter(models.User.username == username).first()
    if user and user.origin != "social":
        # Someone created this name directly on the registry. It is not necessarily the
        # same person as the VibeSocial user, so never hand over its session.
        logger.warning("Refusing brokered session for registry-only account %r", username)
        raise HTTPException(status_code=409, detail=(
            "A separate CopyGuard account already uses this username, so it cannot be linked automatically."))
    if not user:
        user = models.User(username=username, password_hash=auth.unusable_password_hash(), origin="social")
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Raced with another request for the same new user -- reuse the winner.
            db.rollback()
            user = db.query(models.User).filter(models.User.username == username).first()
            if not user:
                raise HTTPException(status_code=500, detail="Could not provision registry account")
        else:
            db.refresh(user)

    token = auth.create_access_token(data={"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer", "username": user.username, "user_id": user.id}


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

    # Each piece of content is registered exactly ONCE. The hash check above only
    # catches a byte-identical file; a screenshot, crop, re-save or re-photograph of
    # registered content sailed through and was minted again:
    #   * by someone else -- that person then "owned" a copy and could post the
    #     original's content freely (found here: one photo under two accounts);
    #   * by the same owner -- two registrations of one picture, so a block could cite
    #     either one, not the one the user registered (found here: #92 and #93).
    # The same matcher that guards uploads decides it, and it fails closed.
    try:
        # Off the event loop: a full-registry scan must not stall concurrent upload checks.
        prior, _, _ = await run_in_threadpool(_find_registered_match, original_path, db)
    except Exception:
        logger.exception("Ownership check failed during registration")
        _cleanup_query_files(original_path)
        raise HTTPException(status_code=503, detail="Ownership check could not be completed")
    if prior is not None:
        _cleanup_query_files(original_path)
        if prior.owner_id == current_user.id:
            raise HTTPException(status_code=409, detail=(
                f"You already registered this content (watermark {prior.watermark_id}, "
                f"tx {prior.tx_hash[:18]}...). It is already protected."
            ))
        prior_owner = db.query(models.User).filter(models.User.id == prior.owner_id).first()
        raise HTTPException(status_code=409, detail=(
            f"This content is already registered by @{prior_owner.username if prior_owner else 'another user'}"
            " and cannot be registered by anyone else."
        ))

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
            await run_in_threadpool(watermark_engine.embed_video_watermark, original_path, watermark_bits, output_path)
        else:
            await run_in_threadpool(watermark_engine.embed_watermark, original_path, watermark_bits, output_path)
    except Exception:
        _cleanup_query_files(original_path)
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
                _cleanup_query_files(original_path)
                os.remove(output_path)
                raise HTTPException(status_code=400, detail="Image already registered on blockchain")
            # Pass `from` explicitly rather than relying on w3.eth.default_account being
            # picked up implicitly -- confirmed this web3.py/Ganache combination rejects
            # the transaction ("from not found; is required") without it, even though
            # default_account is set.
            tx_hash = CopyrightRegistry.functions.registerImage(image_hash, str(current_user.id), watermark_id).transact({"from": w3.eth.default_account})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            tx_hash_hex = Web3.to_hex(tx_hash)  # 0x-prefixed, as block explorers show it
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
        _cleanup_query_files(original_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(status_code=400, detail="Image or video already registered")
    db.refresh(img_record)
    # The ownership check analysed the original; scans only ever use the watermarked copy,
    # so those caches would never be read again.
    _cleanup_analysis_files(original_path)

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

def _orb_candidate_path(img):
    """The stored file to compare a record against: its watermarked copy, else the original."""
    for directory, stored_name in ((WATERMARKED_DIR, img.watermarked_path),
                                   (ORIGINAL_DIR, img.original_path)):
        if not stored_name:
            continue
        try:
            path = upload_utils.safe_join(directory, stored_name)
        except Exception:
            continue
        if os.path.exists(path):
            return path
    return None


BLOCK_CONFIDENCE = 50.0  # a match must exceed this to count as "registered"


class _SkipLayer(Exception):
    """Internal: this evidence layer does not apply to the current upload."""


def _cleanup_analysis_files(path):
    """Remove the ORB sample frames / descriptor caches written beside an analysed file."""
    _remove_files(_analysis_files(path))


def _cleanup_query_files(path):
    """Remove an analysed file plus the ORB sample frames / descriptor caches beside it."""
    _remove_files([path] + _analysis_files(path))


def _analysis_files(path):
    leftovers = [watermark_engine._orb_cache_path(path)]
    for i in range(len(watermark_engine.VIDEO_ORB_SAMPLE_POSITIONS)):
        frame = f"{path}_orbkf{i}.jpg"
        leftovers += [frame, watermark_engine._orb_cache_path(frame)]
    return leftovers


def _remove_files(paths):
    for leftover in paths:
        try:
            if os.path.exists(leftover):
                os.remove(leftover)
        except OSError:
            pass


def _find_registered_match(path, db):
    """
    Find the registered item a file is a copy of: (record, confidence, method) or
    (None, 0.0, None).

    Shared by upload verification and by registration (so content already registered by
    someone else -- including a screenshot or crop of it -- cannot be registered again
    under a new owner).

    Fails CLOSED: a problem with one stored record is logged and that record skipped,
    but if the check itself cannot run the error propagates to the caller instead of
    quietly reporting "not registered". Previously any exception here returned a clean
    "not registered", so a single glitch let protected content straight through.
    """
    WATERMARK_BITS = 8 * 8  # 8 ASCII chars x 8 bits each
    is_video = watermark_engine.is_video_file(path)
    if is_video:
        extracted_bits = watermark_engine.extract_video_watermark(path, WATERMARK_BITS)
        # Videos yield more than one candidate hash so records stored under an older
        # frame convention still compare correctly (see the engine for why).
        phash_strs = lambda n: watermark_engine.get_video_perceptual_hash_candidates(path, hash_size=n)
    else:
        extracted_bits = watermark_engine.extract_watermark(path, WATERMARK_BITS)
        phash_strs = lambda n: [watermark_engine.get_perceptual_hash(path, hash_size=n)]

    extracted_wid = watermark_engine.binary_to_str(extracted_bits)

    # The upload is hashed at the stored record's size. The earliest records hold a
    # 64-bit hash (8x8) while current ones hold 256 bits (16x16); comparing across sizes
    # raised, and the raise skipped the record entirely -- ORB included -- so a copy of
    # an early registration was only caught if its watermark survived intact.
    phash_by_size = {}
    # Featureless uploads (plain colour) have no usable hash; watermark and ORB still run.
    phash_usable = watermark_engine.perceptual_detail(path) >= watermark_engine.MIN_DETAIL_FOR_PHASH

    def uploaded_phashes_at(hash_size):
        if hash_size not in phash_by_size:
            phash_by_size[hash_size] = [watermark_engine.imagehash.hex_to_hash(h) for h in phash_strs(hash_size)]
        return phash_by_size[hash_size]
    all_images = db.query(models.ImageRecord).order_by(models.ImageRecord.id).all()

    # Primary: watermark_id exact match (strongest signal) -- the hidden, invisible
    # DWT-DCT watermark embedded at registration time. Checked against EVERY record
    # before any fuzzy matching runs. Interleaving it into the per-record scan let a
    # strong visual match on an older record end the scan before a newer record whose
    # watermark matched exactly was ever reached -- a block then cited the wrong
    # registration (its watermark, tx and block) even though the right one existed.
    exact = next((img for img in all_images if extracted_wid and extracted_wid == img.watermark_id), None)
    if exact is not None:
        return exact, 99.9, "watermark"

    # Describe the file once and reuse it for every candidate; this is by far the most
    # repeated work in the scan. Lazy, so a perceptual-hash hit can settle it without
    # paying for it. For video this is several frames sampled across the clip.
    query_orb_features = _Lazy(lambda: watermark_engine.compute_orb_features_multi(
        watermark_engine.orb_reference_paths(path)))

    # Every record is compared and the strongest evidence wins -- ranked by confidence,
    # then by how many points actually line up. The scan used to stop at the first
    # record scoring 97+, oldest first; when the same picture had been registered more
    # than once, a copy was then cited against whichever registration came first rather
    # than the one it was actually made from (measured: 317 vs 903 aligned points).
    matched_image, confidence, match_method, evidence = None, 0.0, None, 0
    for img in all_images:
        try:
            # Secondary: perceptual hash similarity (distance <= 8 of 256 bits, the same
            # 1/32 tolerance for older 64-bit hashes). Catches near-identical copies
            # (recompression, minor resize) even if the watermark bits didn't survive.
            # Its own try: a bad stored hash must never skip the ORB check below.
            try:
                if not phash_usable:
                    raise _SkipLayer
                db_phash = watermark_engine.imagehash.hex_to_hash(img.image_hash)
                hash_bits = db_phash.hash.size
                phash_dist = min(candidate - db_phash
                                 for candidate in uploaded_phashes_at(db_phash.hash.shape[0]))
                scaled_dist = phash_dist * 256.0 / hash_bits
                if scaled_dist <= 8:
                    phash_conf = max(60.0, 95.0 - scaled_dist * 4)
                    if (phash_conf, 0) > (confidence, evidence):
                        matched_image, confidence, match_method, evidence = img, phash_conf, "perceptual_hash", 0
            except _SkipLayer:
                pass
            except Exception:
                logger.exception("Perceptual hash unusable for registry record %s; using ORB only", img.id)

            # Tertiary: ORB structural matching -- catches screenshots and camera
            # re-photographs, where watermark and hash are destroyed but the picture's
            # structure still lines up under a geometrically verified homography (see
            # orb_similarity_from_features for the gates that keep coincidences out).
            #
            # Only the watermarked rendition is compared: it is the copy that circulates
            # publicly and differs from the original solely by an invisible watermark
            # (measured: identical scores on every record). The original is only a
            # fallback for records whose watermarked file is missing.
            candidate_path = _orb_candidate_path(img)
            if candidate_path:
                # A failure here is about the UPLOAD, not this record. Skipping it would
                # skip every record and report "not registered" -- letting a screenshot
                # of protected work through. Abort the whole check instead.
                try:
                    query_features = query_orb_features.value
                except Exception as exc:
                    raise _UploadUnreadable("could not extract features from the upload") from exc
                candidate_features = watermark_engine.compute_orb_features_multi(
                    watermark_engine.orb_reference_paths(candidate_path))
                orb_score, inliers = watermark_engine.best_orb_match(query_features, candidate_features)
                if orb_score > 0 and (orb_score, inliers) > (confidence, evidence):
                    matched_image, confidence, match_method, evidence = img, orb_score, "orb_visual_similarity", inliers
        except _UploadUnreadable:
            raise
        except Exception:
            logger.exception("Skipping registry record %s during match scan", img.id)
            continue

    if matched_image is None or confidence <= BLOCK_CONFIDENCE:
        return None, 0.0, None
    return matched_image, confidence, match_method


@app.post("/api/verify-watermark")
@limiter.limit(config.RATE_LIMIT_VERIFY)
async def verify_watermark(request: Request, file: UploadFile = File(...), x_registry_internal: str = Header(None), db: Session = Depends(auth.get_db)):
    if x_registry_internal != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    ext = upload_utils.validate_extension(file.filename)
    temp_path = os.path.join(UPLOAD_DIR, upload_utils.generate_filename("check", "anon", ext))
    await upload_utils.save_upload_streaming(file, temp_path, config.MAX_UPLOAD_SIZE_BYTES)

    try:
        matched_image, confidence, match_method = await run_in_threadpool(_find_registered_match, temp_path, db)
    except Exception:
        # Fail closed: the caller refuses the upload rather than treating an unchecked
        # file as unregistered.
        logger.exception("Copyright check failed")
        raise HTTPException(status_code=503, detail="Copyright check could not be completed")
    finally:
        _cleanup_query_files(temp_path)

    if matched_image:
        owner_id = matched_image.owner_id
        watermark_id = matched_image.watermark_id
        registered_at = utc_iso(matched_image.timestamp)
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
                        registered_at = datetime.fromtimestamp(int(ts_bc), tz=timezone.utc).isoformat()
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
        # preview_token: thumbnails come with the list instead of one token request per asset.
        "images": [{"id": img.id, "watermark_id": img.watermark_id, "tx_hash": img.tx_hash, "timestamp": utc_iso(img.timestamp),
                    "owner_id": img.owner_id, "preview_token": _download_token(current_user, img.id),
                    "is_video": watermark_engine.is_video_file(img.watermarked_path or "")} for img in images]
    }

@app.post("/api/images/{image_id}/download-token")
def create_download_token(image_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    img = db.query(models.ImageRecord).filter(models.ImageRecord.id == image_id, models.ImageRecord.owner_id == current_user.id).first()
    if not img:
        raise HTTPException(status_code=404, detail="File not found")
    return {"token": _download_token(current_user, image_id), "expires_in": config.DOWNLOAD_TOKEN_EXPIRE_SECONDS}


def _download_token(user, image_id):
    """Short-lived token for one file of the user's, usable in a plain <img>/link URL."""
    return auth.create_access_token(
        data={"sub": user.username, "user_id": user.id, "image_id": image_id},
        expires_minutes=config.DOWNLOAD_TOKEN_EXPIRE_SECONDS / 60,
        purpose="download"
    )

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
                    "hash": Web3.to_hex(tx.hash),
                    "from": tx['from'],
                    "to": tx['to'],
                })

            blocks.append({
                "number": block.number,
                "hash": Web3.to_hex(block.hash),
                "parentHash": Web3.to_hex(block.parentHash),
                "timestamp": block.timestamp,
                "transactions": txs
            })

        return {"blocks": blocks}
    except Exception:
        return {"blocks": []}
