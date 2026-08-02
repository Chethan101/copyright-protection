from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .database import engine, SessionLocal, Base
from . import models, auth
import os, uuid, shutil, requests
from fastapi.responses import FileResponse
from pydantic import BaseModel

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
REGISTRY_URL = "http://127.0.0.1:8000/api"

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...), db: Session = Depends(auth.get_db)):
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    user = models.User(username=username, password_hash=auth.get_password_hash(password))
    db.add(user); db.commit()
    return {"msg": "Registered successfully"}

@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(auth.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect credentials")
    token = auth.create_access_token(data={"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer", "username": user.username, "user_id": user.id}

# ── Posts ─────────────────────────────────────────────────────────────────────

def _post_dict(p: models.Post, db: Session, current_user_id: int = None):
    uploader = db.query(models.User).filter(models.User.id == p.uploader_id).first()
    liked = False
    if current_user_id:
        liked = db.query(models.Like).filter(models.Like.post_id == p.id, models.Like.user_id == current_user_id).first() is not None
    comments = []
    for c in sorted(p.comments, key=lambda x: x.timestamp):
        commenter = db.query(models.User).filter(models.User.id == c.user_id).first()
        comments.append({"id": c.id, "username": commenter.username if commenter else "?", "text": c.text, "timestamp": c.timestamp.isoformat()})
    return {
        "id": p.id,
        "uploader": uploader.username if uploader else "Unknown",
        "uploader_id": p.uploader_id,
        "image_url": f"http://localhost:8001/api/images/{p.image_path}",
        "caption": p.caption or "",
        "timestamp": p.timestamp.isoformat(),
        "likes_count": len(p.likes),
        "liked": liked,
        "comments": comments,
        "comments_count": len(p.comments),
        "repost_of": p.repost_of,
    }

@app.post("/api/posts/upload")
async def upload_post(
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(auth.get_db)
):
    temp_path = os.path.join(UPLOAD_DIR, f"check_{uuid.uuid4().hex[:8]}_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        with open(temp_path, "rb") as f:
            resp = requests.post(f"{REGISTRY_URL}/verify-watermark", files={"file": (file.filename, f, file.content_type)}, timeout=15)
            resp.raise_for_status()
            verification_result = resp.json()
    except Exception as e:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Registry check failed: {str(e)}")

    if verification_result.get("is_registered") and verification_result.get("owner_name") != current_user.username:
        log = models.ViolationLog(
            attempted_by_id=current_user.id,
            original_owner_id=verification_result.get("owner_id"),
            original_owner_name=verification_result.get("owner_name"),
            image_id=str(verification_result.get("image_id")),
            tx_hash=verification_result.get("tx_hash"),
            confidence_score=verification_result.get("confidence"),
            reason="Unauthorized Upload Attempt"
        )
        db.add(log); db.commit()
        os.remove(temp_path)
        raise HTTPException(status_code=403, detail={
            "message": "Copyright Protected Content",
            "owner_name": verification_result.get("owner_name"),
            "owner_id": verification_result.get("owner_id"),
            "tx_id": verification_result.get("tx_hash"),
            "timestamp": verification_result.get("timestamp"),
            "confidence": verification_result.get("confidence")
        })

    post_filename = f"post_{current_user.id}_{uuid.uuid4().hex[:8]}_{file.filename}"
    os.rename(temp_path, os.path.join(UPLOAD_DIR, post_filename))
    new_post = models.Post(uploader_id=current_user.id, image_path=post_filename, caption=caption)
    db.add(new_post); db.commit(); db.refresh(new_post)
    return {"msg": "Upload Successful", "post_id": new_post.id}

@app.get("/api/feed")
def get_feed(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    posts = db.query(models.Post).order_by(models.Post.timestamp.desc()).all()
    return {"posts": [_post_dict(p, db, current_user.id) for p in posts]}

@app.get("/api/profile/{username}")
def get_profile(username: str, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    posts = db.query(models.Post).filter(models.Post.uploader_id == user.id).order_by(models.Post.timestamp.desc()).all()
    return {
        "user": {"id": user.id, "username": user.username, "bio": user.bio or ""},
        "posts": [_post_dict(p, db, current_user.id) for p in posts],
        "posts_count": len(posts)
    }

# ── Likes ─────────────────────────────────────────────────────────────────────

@app.post("/api/posts/{post_id}/like")
def toggle_like(post_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    existing = db.query(models.Like).filter(models.Like.post_id == post_id, models.Like.user_id == current_user.id).first()
    if existing:
        db.delete(existing); db.commit()
        return {"liked": False, "likes_count": db.query(models.Like).filter(models.Like.post_id == post_id).count()}
    else:
        like = models.Like(user_id=current_user.id, post_id=post_id)
        db.add(like); db.commit()
        return {"liked": True, "likes_count": db.query(models.Like).filter(models.Like.post_id == post_id).count()}

# ── Comments ──────────────────────────────────────────────────────────────────

class CommentBody(BaseModel):
    text: str

@app.post("/api/posts/{post_id}/comment")
def add_comment(post_id: int, body: CommentBody, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    comment = models.Comment(user_id=current_user.id, post_id=post_id, text=body.text.strip())
    db.add(comment); db.commit(); db.refresh(comment)
    return {"id": comment.id, "username": current_user.username, "text": comment.text, "timestamp": comment.timestamp.isoformat()}

@app.delete("/api/comments/{comment_id}")
def delete_comment(comment_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your comment")
    db.delete(comment); db.commit()
    return {"msg": "Deleted"}

# ── Repost ────────────────────────────────────────────────────────────────────

@app.post("/api/posts/{post_id}/repost")
def repost(post_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    original = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Post not found")
    # Check if user already reposted
    already = db.query(models.Post).filter(models.Post.repost_of == post_id, models.Post.uploader_id == current_user.id).first()
    if already:
        raise HTTPException(status_code=400, detail="Already reposted")
    new_post = models.Post(uploader_id=current_user.id, image_path=original.image_path, caption=f"🔁 Repost from @{db.query(models.User).filter(models.User.id == original.uploader_id).first().username}", repost_of=post_id)
    db.add(new_post); db.commit()
    return {"msg": "Reposted successfully"}

# ── Notifications / Violations ────────────────────────────────────────────────

@app.get("/api/violations")
def get_violations(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    violations = db.query(models.ViolationLog).filter(models.ViolationLog.attempted_by_id == current_user.id).order_by(models.ViolationLog.timestamp.desc()).all()
    alerts = db.query(models.ViolationLog).filter(models.ViolationLog.original_owner_id == current_user.id).order_by(models.ViolationLog.timestamp.desc()).all()
    def v_dict(v):
        return {"id": v.id, "attempted_by_id": v.attempted_by_id, "original_owner_name": v.original_owner_name, "tx_hash": v.tx_hash, "confidence_score": v.confidence_score, "reason": v.reason, "timestamp": v.timestamp.isoformat()}
    return {"my_violations": [v_dict(v) for v in violations], "notifications": [v_dict(v) for v in alerts]}

# ── Static images ─────────────────────────────────────────────────────────────

@app.get("/api/images/{image_name}")
def serve_image(image_name: str):
    file_path = os.path.join(UPLOAD_DIR, image_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(file_path, media_type="image/jpeg")
