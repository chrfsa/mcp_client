from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()

class ServerConfigModel(Base):
    __tablename__ = 'server_configs'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    transport = Column(String, nullable=False)
    config = Column(JSON, nullable=False)  # Stores the full config dict
    created_at = Column(DateTime, default=datetime.utcnow)

class SessionModel(Base):
    __tablename__ = 'sessions'
    
    id = Column(String, primary_key=True)  # UUID
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship("MessageModel", back_populates="session", cascade="all, delete-orphan")

class MessageModel(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String, ForeignKey('sessions.id'), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    tool_call_id = Column(String, nullable=True)
    name = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("SessionModel", back_populates="messages")

# Database setup
DATABASE_URL = "sqlite:///./mcp_client.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
