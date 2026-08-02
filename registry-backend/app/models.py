from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    images = relationship("ImageRecord", back_populates="owner")

class ImageRecord(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True, index=True)  # Image ID
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    watermark_id = Column(String, nullable=False, index=True)
    image_hash = Column(String, unique=True, index=True, nullable=False)
    tx_hash = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    watermarked_path = Column(String, nullable=False)
    original_path = Column(String, nullable=False)
    owner = relationship("User", back_populates="images")
