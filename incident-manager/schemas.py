from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# Alert Webhook Schemas
class Alert(BaseModel):
    status: str
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    fingerprint: Optional[str] = None

class WebhookPayload(BaseModel):
    alerts: List[Alert] = Field(default_factory=list)

# Incident Response Schema
class IncidentResponse(BaseModel):
    id: int
    incident_id: str
    service: str
    severity: str
    status: str
    started_at: datetime
    resolved_at: Optional[datetime] = None
    root_cause: Optional[str] = None
    confidence: Optional[float] = None
    symptoms: List[Any] = Field(default_factory=list)

    class Config:
        from_attributes = True

# Incident Update Schema
class IncidentUpdate(BaseModel):
    root_cause: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
