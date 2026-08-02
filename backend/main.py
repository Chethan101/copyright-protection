from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import engine, SessionLocal, init_db
import models
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
import os
import uuid
import json
from web3 import Web3
from watermark_engine import embed_watermark, extract_watermark, get_perceptual_hash, calculate_orb_similarity, str_to_binary, binary_to_str
import shutil
import imagehash

init_db()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Web3 Setup
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:7545'))
w3.eth.default_account = w3.eth.accounts[0]
contract_info_path = os.path.join(os.path.dirname(__file__), 'contract_info.json')
CopyrightRegistry = None
if os.path.exists(contract_info_path):
    with open(contract_info_path, 'r') as f:
        contract_data = json.load(f)
        CopyrightRegistry = w3.eth.contract(address=contract_data['address'], abi=contract_data['abi'])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
WATERMARKED_DIR = os.path.join(os.path.dirname(__file__), 'watermarked')
os.makedirs(WATERMARKED_DIR, exist_ok=True)
ORIGINAL_DIR = os.path.join(os.path.dirname(__file__), 'originals')
os.makedirs(ORIGINAL_DIR, exist_ok=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@app.post("/register")
def register(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    user = models.User(username=username, password_hash=pwd_context.hash(password))
    db.add(user)
    db.commit()
    return {"msg": "Registered"}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect credentials")
    token = jwt.encode({"sub": user.username, "user_id": user.id, "exp": datetime.utcnow() + timedelta(minutes=60)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

@app.post("/upload")
async def upload_image(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Save Original
    original_filename = f"orig_{current_user.id}_{file.filename}"
    original_path = os.path.join(ORIGINAL_DIR, original_filename)
    with open(original_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    image_hash = get_perceptual_hash(original_path)
    
    owner_id, wm_id, ts, is_reg = CopyrightRegistry.functions.verifyImage(image_hash).call()
    if is_reg:
        os.remove(original_path)
        raise HTTPException(status_code=400, detail="Image already registered")
        
    watermark_id = str(uuid.uuid4())[:8]
    # Watermark payload contains only WID (8 chars = 64 bits). 
    watermark_bits = str_to_binary(watermark_id)
    
    output_filename = f"wm_{current_user.id}_{file.filename}"
    output_path = os.path.join(WATERMARKED_DIR, output_filename)
    embed_watermark(original_path, watermark_bits, output_path)
    
    tx_hash = CopyrightRegistry.functions.registerImage(image_hash, str(current_user.id), watermark_id).transact()
    w3.eth.wait_for_transaction_receipt(tx_hash)
    
    img_record = models.ImageRecord(owner_id=current_user.id, image_hash=image_hash, watermark_id=watermark_id, transaction_hash=tx_hash.hex(), file_name=output_filename, original_file_name=original_filename)
    db.add(img_record)
    db.commit()
    
    return {"msg": "Success", "image_hash": image_hash, "tx_hash": tx_hash.hex()}

@app.post("/social/verify")
async def verify_upload(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    temp_path = os.path.join(UPLOAD_DIR, f"check_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    uploaded_phash = imagehash.hex_to_hash(get_perceptual_hash(temp_path))
    
    # 1. DWT-DCT Extraction
    extracted_bits = extract_watermark(temp_path, 64)
    extracted_wid = binary_to_str(extracted_bits)
    
    # 2. Hybrid Verification Engine
    matched_image = None
    confidence = 0.0
    
    all_images = db.query(models.ImageRecord).all()
    
    for img in all_images:
        # A. Watermark Match
        if img.watermark_id == extracted_wid:
            matched_image = img
            confidence = 99.0
            break
            
        # B. pHash Match
        db_phash = imagehash.hex_to_hash(img.image_hash)
        if uploaded_phash - db_phash <= 5: # Very similar
            matched_image = img
            confidence = max(confidence, 95.0)
            
        # C. ORB Feature Match
        orig_path = os.path.join(ORIGINAL_DIR, img.original_file_name)
        if os.path.exists(orig_path):
            orb_score = calculate_orb_similarity(temp_path, orig_path)
            if orb_score > 30.0:
                matched_image = img
                confidence = max(confidence, orb_score)
                
    if matched_image and confidence > 50.0:
        # Verification found a match! Check ownership
        owner_id, wm_id, ts, is_reg = CopyrightRegistry.functions.verifyImage(matched_image.image_hash).call()
        
        if is_reg and owner_id != str(current_user.id):
            owner_user = db.query(models.User).filter(models.User.id == int(owner_id)).first()
            
            # Log Violation
            log = models.VerificationLog(
                attempted_by_id=current_user.id,
                original_owner_id=int(owner_id),
                transaction_hash=matched_image.transaction_hash,
                image_hash=matched_image.image_hash,
                watermark_id=matched_image.watermark_id,
                status="BLOCKED",
                reason="Unauthorized Upload Attempt",
                confidence_score=confidence
            )
            db.add(log)
            db.commit()
            
            os.remove(temp_path)
            raise HTTPException(status_code=403, detail={
                "message": "Copyright Protected Image Detected",
                "owner_name": owner_user.username if owner_user else "Unknown",
                "owner_id": owner_id,
                "tx_id": matched_image.transaction_hash,
                "timestamp": matched_image.timestamp.isoformat(),
                "confidence": confidence
            })
            
        elif is_reg and owner_id == str(current_user.id):
            post = models.SocialPost(uploader_id=current_user.id, file_name=file.filename)
            db.add(post)
            db.commit()
            os.remove(temp_path)
            return {"msg": "Ownership Verified. Blockchain Verified. Upload Successful"}
            
    # Allow normally if no match
    post = models.SocialPost(uploader_id=current_user.id, file_name=file.filename)
    db.add(post)
    db.commit()
    os.remove(temp_path)
    return {"msg": "No registered copyright watermark detected. Upload Successful."}

@app.get("/dashboard")
def get_dashboard(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    images = db.query(models.ImageRecord).filter(models.ImageRecord.owner_id == current_user.id).all()
    return {"user_id": current_user.id, "username": current_user.username, "registered_images": len(images), "images": images}

@app.get("/download/{image_id}")
def download_image(image_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    img = db.query(models.ImageRecord).filter(models.ImageRecord.id == image_id, models.ImageRecord.owner_id == current_user.id).first()
    if not img or not img.file_name:
        raise HTTPException(status_code=404, detail="Image not found")
    file_path = os.path.join(WATERMARKED_DIR, img.file_name)
    return FileResponse(file_path, media_type="image/jpeg", filename=img.file_name)

@app.get("/social/dashboard")
def social_dashboard(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    posts = db.query(models.SocialPost).filter(models.SocialPost.uploader_id == current_user.id).order_by(models.SocialPost.timestamp.desc()).all()
    logs = db.query(models.VerificationLog).filter(models.VerificationLog.attempted_by_id == current_user.id).order_by(models.VerificationLog.timestamp.desc()).all()
    
    my_images = [img.image_hash for img in db.query(models.ImageRecord).filter(models.ImageRecord.owner_id == current_user.id).all()]
    notifications = db.query(models.VerificationLog).filter(models.VerificationLog.image_hash.in_(my_images), models.VerificationLog.attempted_by_id != current_user.id).order_by(models.VerificationLog.timestamp.desc()).all()
    
    formatted_notifs = []
    for notif in notifications:
        attempter = db.query(models.User).filter(models.User.id == notif.attempted_by_id).first()
        formatted_notifs.append({
            "id": notif.id,
            "attempted_by": attempter.username if attempter else "Unknown",
            "image_hash": notif.image_hash,
            "timestamp": notif.timestamp,
            "confidence": notif.confidence_score,
            "tx_hash": notif.transaction_hash
        })
        
    return {
        "posts": posts,
        "logs": logs,
        "notifications": formatted_notifs
    }

@app.get("/blockchain/blocks")
def get_blockchain_blocks():
    """Returns recent blocks and transactions from Ganache"""
    latest_block = w3.eth.block_number
    blocks = []
    
    # Fetch last 10 blocks
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
