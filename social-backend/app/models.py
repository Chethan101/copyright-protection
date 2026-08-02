from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    bio = Column(String, default="")
    avatar_color = Column(String, default="#8b5cf6")
    posts = relationship("Post", back_populates="uploader", foreign_keys="Post.uploader_id")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    image_path = Column(String, nullable=False)
    caption = Column(Text, default="")
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Integer, default=1)
    repost_of = Column(Integer, ForeignKey("posts.id"), nullable=True)
    uploader = relationship("User", back_populates="posts", foreign_keys=[uploader_id])
    likes = relationship("Like", back_populates="post", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_like"),)
    post = relationship("Post", back_populates="likes")
    user = relationship("User")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    post = relationship("Post", back_populates="comments")
    user = relationship("User")

class ViolationLog(Base):
    __tablename__ = "violation_logs"
    id = Column(Integer, primary_key=True, index=True)
    attempted_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_owner_id = Column(Integer, nullable=True)
    original_owner_name = Column(String, nullable=True)
    image_id = Column(String, nullable=True)
    tx_hash = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=True)
    reason = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    attempted_by = relationship("User")
