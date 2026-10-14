import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

Base = declarative_base()

class DocumentRecord(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, default="uploaded")
    created_at = Column(DateTime, default=datetime.utcnow)

class AnalysisRecord(Base):
    __tablename__ = "analysis_results"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, index=True, nullable=False)
    document_type = Column(String, nullable=False)
    classification_confidence = Column(Float, nullable=False)
    verification_status = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=True)
    fields_json = Column(Text, default="{}")
    findings_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def fields(self):
        try:
            return json.loads(self.fields_json or "{}")
        except Exception:
            return {}

    @property
    def findings(self):
        try:
            return json.loads(self.findings_json or "[]")
        except Exception:
            return []

db_url = settings.get_database_url
engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
