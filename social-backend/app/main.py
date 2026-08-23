from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from .database import engine, Base
from . import models, auth, upload_utils, config
import os, uuid, requests
from fastapi.responses import FileResponse
from pydantic import BaseModel

Base.metadata.create_all(bind=engine)

if engine.dialect.name == "sqlite":
    # No migration framework in this project; additive SQLite columns are cheap
    # and safe to backfill here so pre-existing DBs pick up new model fields.
    with engine.connect() as conn:
        existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(violation_logs)"))}
        if existing_cols and "match_method" not in existing_cols:
            conn.execute(text("ALTER TABLE violation_logs ADD COLUMN match_method VARCHAR"))
            conn.commit()

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

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
REGISTRY_URL = config.REGISTRY_URL

# ── Auth ──────────────────────────────────────────────────────────────────────

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
    token = auth.create_access_token(data={"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer", "username": user.username, "user_id": user.id}

# ── Posts ─────────────────────────────────────────────────────────────────────

def _post_dict(p: models.Post, db: Session, current_user_id: int = None):
    uploader = db.query(models.User).filter(models.User.id == p.uploader_id).first()
    liked = False
    saved = False
    if current_user_id:
        liked = db.query(models.Like).filter(models.Like.post_id == p.id, models.Like.user_id == current_user_id).first() is not None
        saved = db.query(models.SavedPost).filter(models.SavedPost.post_id == p.id, models.SavedPost.user_id == current_user_id).first() is not None
    comments = []
    for c in sorted(p.comments, key=lambda x: x.timestamp):
        commenter = db.query(models.User).filter(models.User.id == c.user_id).first()
        comments.append({"id": c.id, "user_id": c.user_id, "username": commenter.username if commenter else "?", "text": c.text, "timestamp": c.timestamp.isoformat()})
    return {
        "id": p.id,
        "uploader": uploader.username if uploader else "Unknown",
        "uploader_id": p.uploader_id,
        "image_url": f"/api/images/{p.image_path}",
        "caption": p.caption or "",
        "timestamp": p.timestamp.isoformat(),
        "likes_count": len(p.likes),
        "liked": liked,
        "saved": saved,
        "comments": comments,
        "comments_count": len(p.comments),
        "repost_of": p.repost_of,
        "is_owner": current_user_id == p.uploader_id,
    }

@app.post("/api/posts/upload")
@limiter.limit(config.RATE_LIMIT_UPLOAD)
async def upload_post(
    request: Request,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(auth.get_db)
):
    ext = upload_utils.validate_extension(file.filename)
    temp_path = os.path.join(UPLOAD_DIR, upload_utils.generate_filename("check", current_user.id, ext))
    await upload_utils.save_upload_streaming(file, temp_path, config.MAX_UPLOAD_SIZE_BYTES)

    try:
        with open(temp_path, "rb") as f:
            resp = requests.post(
                f"{REGISTRY_URL}/verify-watermark",
                files={"file": (file.filename, f, file.content_type)},
                headers={"x-registry-internal": config.INTERNAL_API_KEY},
                timeout=config.REGISTRY_TIMEOUT_SECONDS
            )
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
            match_method=verification_result.get("match_method"),
            reason="Unauthorized Upload Attempt"
        )
        db.add(log); db.commit()
        os.remove(temp_path)
        raise HTTPException(status_code=403, detail={
            "message": "Copyright Protected Content",
            "owner_name": verification_result.get("owner_name"),
            "owner_id": verification_result.get("owner_id"),
            "owner_source": verification_result.get("owner_source"),
            "watermark_id": verification_result.get("watermark_id"),
            "tx_id": verification_result.get("tx_hash"),
            "timestamp": verification_result.get("timestamp"),
            "confidence": verification_result.get("confidence"),
            "match_method": verification_result.get("match_method"),
            "blockchain_verified": verification_result.get("blockchain_verified")
        })

    post_filename = upload_utils.generate_filename("post", current_user.id, ext)
    os.rename(temp_path, os.path.join(UPLOAD_DIR, post_filename))
    new_post = models.Post(uploader_id=current_user.id, image_path=post_filename, caption=caption)
    db.add(new_post); db.commit(); db.refresh(new_post)
    return {"msg": "Upload Successful", "post_id": new_post.id}

@app.get("/api/feed")
def get_feed(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    posts = db.query(models.Post).order_by(models.Post.timestamp.desc()).all()
    return {"posts": [_post_dict(p, db, current_user.id) for p in posts]}

@app.delete("/api/posts/{post_id}")
def delete_post(post_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.uploader_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own posts")

    image_path = post.image_path
    # Reposts of this post copy its file reference rather than owning a separate upload
    # (see /posts/{id}/repost). Detach them into standalone posts instead of leaving a
    # dangling repost_of, matching how reposts behave on real platforms when the
    # original is removed -- the repost itself is not deleted.
    db.query(models.Post).filter(models.Post.repost_of == post_id).update({"repost_of": None})
    db.delete(post)  # cascades likes/comments/saves via the model relationships
    db.commit()

    # Only remove the file if no other post (a repost, or this same file reposted
    # again) still references it.
    still_referenced = db.query(models.Post).filter(models.Post.image_path == image_path).first()
    if not still_referenced:
        file_path = upload_utils.safe_join(UPLOAD_DIR, image_path)
        if os.path.exists(file_path):
            os.remove(file_path)

    return {"msg": "Post deleted"}

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
        db.add(like)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # Already liked concurrently — idempotent, treat as success
        return {"liked": True, "likes_count": db.query(models.Like).filter(models.Like.post_id == post_id).count()}

# ── Saves / Bookmarks ─────────────────────────────────────────────────────────

@app.post("/api/posts/{post_id}/save")
def toggle_save(post_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    existing = db.query(models.SavedPost).filter(models.SavedPost.post_id == post_id, models.SavedPost.user_id == current_user.id).first()
    if existing:
        db.delete(existing); db.commit()
        return {"saved": False}
    else:
        save = models.SavedPost(user_id=current_user.id, post_id=post_id)
        db.add(save)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # Already saved concurrently -- idempotent, treat as success
        return {"saved": True}

@app.get("/api/saved")
def get_saved(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    saves = db.query(models.SavedPost).filter(models.SavedPost.user_id == current_user.id).order_by(models.SavedPost.timestamp.desc()).all()
    posts = [s.post for s in saves if s.post is not None]
    return {"posts": [_post_dict(p, db, current_user.id) for p in posts]}

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
    # original_owner_id is registry-backend's user id, from registry's own independent
    # users table -- it has no relationship to this service's ids and must never be
    # compared against current_user.id here. original_owner_name (a plain username
    # string) is the only field both services agree on; match on that instead.
    alerts = db.query(models.ViolationLog).filter(models.ViolationLog.original_owner_name == current_user.username).order_by(models.ViolationLog.timestamp.desc()).all()
    def v_dict(v):
        return {"id": v.id, "attempted_by_id": v.attempted_by_id, "original_owner_name": v.original_owner_name, "tx_hash": v.tx_hash, "confidence_score": v.confidence_score, "match_method": v.match_method, "reason": v.reason, "timestamp": v.timestamp.isoformat()}
    return {"my_violations": [v_dict(v) for v in violations], "notifications": [v_dict(v) for v in alerts]}

# ── Static images ─────────────────────────────────────────────────────────────

@app.get("/api/images/{image_name}")
def serve_image(image_name: str):
    file_path = upload_utils.safe_join(UPLOAD_DIR, image_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type=upload_utils.media_type_for(file_path))
