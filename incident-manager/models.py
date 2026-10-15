from sqlalchemy import Column, Integer, String, DateTime, Float, JSON
from database import Base

class Incident(Base):
    __tablename__ = "incidents"
    
    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String, unique=True, index=True)
    service = Column(String)
    severity = Column(String)
    status = Column(String)
    started_at = Column(DateTime)
    resolved_at = Column(DateTime, nullable=True)
    root_cause = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    symptoms = Column(JSON)
