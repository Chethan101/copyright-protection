from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)

class ImageRecord(Base):
    __tablename__ = 'images'
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('users.id'))
    image_hash = Column(String, unique=True, index=True)
    watermark_id = Column(String)
    transaction_hash = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    file_name = Column(String)
    original_file_name = Column(String)
    
    owner = relationship("User")

class SocialPost(Base):
    __tablename__ = 'social_posts'
    id = Column(Integer, primary_key=True, index=True)
    uploader_id = Column(Integer, ForeignKey('users.id'))
    file_name = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    uploader = relationship("User")

class VerificationLog(Base):
    __tablename__ = 'verification_logs'
    id = Column(Integer, primary_key=True, index=True)
    attempted_by_id = Column(Integer, ForeignKey('users.id'))
    original_owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    transaction_hash = Column(String, nullable=True)
    image_hash = Column(String)
    watermark_id = Column(String, nullable=True)
    status = Column(String) # 'ALLOWED' or 'BLOCKED'
    reason = Column(String)
    confidence_score = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    attempted_by = relationship("User", foreign_keys=[attempted_by_id])
    original_owner = relationship("User", foreign_keys=[original_owner_id])
