from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from .database import engine, SessionLocal, Base
from . import models, auth, watermark_engine
import json, os, uuid, shutil
from web3 import Web3

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:7545'))
try:
    w3.eth.default_account = w3.eth.accounts[0]
except Exception:
    pass
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

INTERNAL_API_KEY = "secret_internal_key"

@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...), db: Session = Depends(auth.get_db)):
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    user = models.User(username=username, password_hash=auth.get_password_hash(password))
    db.add(user)
    db.commit()
    return {"msg": "Registered successfully"}

@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(auth.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect credentials")
    access_token = auth.create_access_token(data={"sub": user.username, "user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/images/register")
async def register_image(file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    original_filename = f"orig_{current_user.id}_{uuid.uuid4().hex[:8]}_{file.filename}"
    original_path = os.path.join(ORIGINAL_DIR, original_filename)
    with open(original_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    is_video = watermark_engine.is_video_file(original_path)
    if is_video:
        image_hash = watermark_engine.get_video_perceptual_hash(original_path)
    else:
        image_hash = watermark_engine.get_perceptual_hash(original_path)
    
    # Check if already registered in DB first
    existing = db.query(models.ImageRecord).filter(models.ImageRecord.image_hash == image_hash).first()
    if existing:
        os.remove(original_path)
        raise HTTPException(status_code=400, detail="Image or video already registered")

    # Generate watermark_id FIRST so it's consistent in both DB and blockchain
    watermark_id = str(uuid.uuid4())[:8]
    watermark_bits = watermark_engine.str_to_binary(watermark_id)
    output_filename = f"wm_{current_user.id}_{uuid.uuid4().hex[:8]}_{file.filename}"
    output_path = os.path.join(WATERMARKED_DIR, output_filename)
    
    if is_video:
        watermark_engine.embed_video_watermark(original_path, watermark_bits, output_path)
    else:
        watermark_engine.embed_watermark(original_path, watermark_bits, output_path)

    # Try blockchain registration with correct watermark_id
    tx_hash_hex = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}"
    block_number = 0
    if CopyrightRegistry:
        try:
            owner_id, wm_id, ts, is_reg = CopyrightRegistry.functions.verifyImage(image_hash).call()
            if is_reg:
                os.remove(original_path)
                os.remove(output_path)
                raise HTTPException(status_code=400, detail="Image already registered on blockchain")
            tx_hash = CopyrightRegistry.functions.registerImage(image_hash, str(current_user.id), watermark_id).transact()
            w3.eth.wait_for_transaction_receipt(tx_hash)
            tx_hash_hex = tx_hash.hex()
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            block_number = receipt.blockNumber
        except HTTPException:
            raise
        except Exception as e:
            pass  # Blockchain unavailable, continue with DB-only registration

    img_record = models.ImageRecord(owner_id=current_user.id, image_hash=image_hash, watermark_id=watermark_id, tx_hash=tx_hash_hex, watermarked_path=output_filename, original_path=original_filename)
    db.add(img_record)
    db.commit()
    db.refresh(img_record)
    
    return {
        "msg": "Transaction Successful", 
        "image_id": img_record.id,
        "image_hash": image_hash, 
        "tx_hash": tx_hash_hex,
        "owner_id": current_user.id,
        "watermark_id": watermark_id,
        "block_number": block_number
    }

@app.post("/api/verify-watermark")
async def verify_watermark(file: UploadFile = File(...), db: Session = Depends(auth.get_db)):
    temp_path = os.path.join(UPLOAD_DIR, f"check_{uuid.uuid4().hex[:8]}_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    matched_image = None
    confidence = 0.0

    try:
        WATERMARK_BITS = 8 * 8  # 8 ASCII chars × 8 bits each
        is_video = watermark_engine.is_video_file(temp_path)

        # Step 1: Extract watermark ID
        if is_video:
            extracted_bits = watermark_engine.extract_video_watermark(temp_path, WATERMARK_BITS)
            uploaded_phash_str = watermark_engine.get_video_perceptual_hash(temp_path)
            kf_path = temp_path + "_keyframe.jpg"
            watermark_engine.extract_keyframe(temp_path, kf_path)
            orb_test_path = kf_path if os.path.exists(kf_path) else temp_path
        else:
            extracted_bits = watermark_engine.extract_watermark(temp_path, WATERMARK_BITS)
            uploaded_phash_str = watermark_engine.get_perceptual_hash(temp_path)
            orb_test_path = temp_path

        extracted_wid = watermark_engine.binary_to_str(extracted_bits)
        uploaded_phash = watermark_engine.imagehash.hex_to_hash(uploaded_phash_str)

        all_images = db.query(models.ImageRecord).all()

        for img in all_images:
            # Primary: watermark_id exact match (strongest signal)
            if extracted_wid and len(extracted_wid) >= 4 and img.watermark_id.startswith(extracted_wid[:4]):
                matched_image = img
                confidence = 99.5
                break

            if extracted_wid == img.watermark_id:
                matched_image = img
                confidence = 99.9
                break

            # Secondary: perceptual hash similarity (phash distance <= 8 out of 256 bits)
            try:
                db_phash = watermark_engine.imagehash.hex_to_hash(img.image_hash)
                phash_dist = uploaded_phash - db_phash
                if phash_dist <= 8:
                    phash_conf = max(60.0, 95.0 - phash_dist * 4)
                    if phash_conf > confidence:
                        matched_image = img
                        confidence = phash_conf
            except Exception:
                pass

            # Tertiary: ORB structural feature matching against original
            orig_path = os.path.join(ORIGINAL_DIR, img.original_path)
            if os.path.exists(orig_path):
                # If orig_path is a video, extract its keyframe for ORB matching
                if watermark_engine.is_video_file(orig_path):
                    orig_kf = orig_path + "_keyframe.jpg"
                    if not os.path.exists(orig_kf):
                        watermark_engine.extract_keyframe(orig_path, orig_kf)
                    target_orig_path = orig_kf if os.path.exists(orig_kf) else orig_path
                else:
                    target_orig_path = orig_path

                orb_score = watermark_engine.calculate_orb_similarity(orb_test_path, target_orig_path)
                if orb_score > 25.0 and orb_score > confidence:
                    matched_image = img
                    confidence = orb_score

            # Also compare against watermarked version
            wm_path = os.path.join(WATERMARKED_DIR, img.watermarked_path)
            if os.path.exists(wm_path):
                if watermark_engine.is_video_file(wm_path):
                    wm_kf = wm_path + "_keyframe.jpg"
                    if not os.path.exists(wm_kf):
                        watermark_engine.extract_keyframe(wm_path, wm_kf)
                    target_wm_path = wm_kf if os.path.exists(wm_kf) else wm_path
                else:
                    target_wm_path = wm_path

                orb_score_wm = watermark_engine.calculate_orb_similarity(orb_test_path, target_wm_path)
                if orb_score_wm > 25.0 and orb_score_wm > confidence:
                    matched_image = img
                    confidence = orb_score_wm

    except Exception as e:
        pass
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            kf_path = temp_path + "_keyframe.jpg"
            if os.path.exists(kf_path):
                os.remove(kf_path)
        except Exception:
            pass

    if matched_image and confidence > 50.0:
        owner_user = db.query(models.User).filter(models.User.id == matched_image.owner_id).first()
        
        blockchain_verified = False
        if CopyrightRegistry:
            try:
                owner_id_bc, wm_id_bc, ts_bc, is_reg = CopyrightRegistry.functions.verifyImage(matched_image.image_hash).call()
                blockchain_verified = is_reg
            except Exception:
                blockchain_verified = True

        return {
            "is_registered": True,
            "watermark_id": matched_image.watermark_id,
            "image_id": matched_image.id,
            "owner_id": matched_image.owner_id,
            "owner_name": owner_user.username if owner_user else "Unknown",
            "tx_hash": matched_image.tx_hash,
            "timestamp": matched_image.timestamp.isoformat(),
            "confidence": round(confidence, 2),
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

@app.get("/api/images/{image_id}/download")
def download_image(image_id: int, token: str, db: Session = Depends(auth.get_db)):
    import jwt as pyjwt
    try:
        payload = pyjwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username = payload.get("sub")
        current_user = db.query(models.User).filter(models.User.username == username).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    img = db.query(models.ImageRecord).filter(models.ImageRecord.id == image_id, models.ImageRecord.owner_id == current_user.id).first()
    if not img or not img.watermarked_path:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = os.path.join(WATERMARKED_DIR, img.watermarked_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    media_type = "video/mp4" if watermark_engine.is_video_file(file_path) else "image/jpeg"
    return FileResponse(file_path, media_type=media_type, filename=img.watermarked_path)

@app.get("/api/blockchain/blocks")
def get_blockchain_blocks():
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

@app.get("/api/internal/image/{image_id}")
def get_internal_image(image_id: int, x_registry_internal: str = Header(None), db: Session = Depends(auth.get_db)):
    if x_registry_internal != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    img = db.query(models.ImageRecord).filter(models.ImageRecord.id == image_id).first()
    if not img or not img.original_path:
        raise HTTPException(status_code=404, detail="Image not found")
    file_path = os.path.join(ORIGINAL_DIR, img.original_path)
    return FileResponse(file_path, media_type="image/jpeg")
