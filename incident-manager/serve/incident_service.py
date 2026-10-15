from sqlalchemy.orm import Session
from datetime import datetime
from models import Incident

def process_webhook_alerts(payload: dict, db: Session):
    for alert in payload.get('alerts', []):
        status = alert.get('status')
        labels = alert.get('labels', {})
        annotations = alert.get('annotations', {})
        
        fingerprint = alert.get('fingerprint', str(datetime.utcnow().timestamp()))
        incident_id = f"INC-{fingerprint[:8]}"
        
        existing = db.query(Incident).filter(Incident.incident_id == incident_id).first()
        
        if status == 'firing' and not existing:
            new_incident = Incident(
                incident_id=incident_id,
                service=labels.get('job', 'unknown'),
                severity=labels.get('severity', 'high'),
                status='open',
                started_at=datetime.utcnow(),
                symptoms=[annotations.get('description', 'Unknown anomaly')]
            )
            db.add(new_incident)
        elif status == 'resolved' and existing:
            existing.status = 'resolved'
            existing.resolved_at = datetime.utcnow()
            
    db.commit()
    return {"message": "Webhook processed"}

def get_all_incidents(db: Session):
    return db.query(Incident).all()

def update_incident_details(incident_id: str, payload: dict, db: Session):
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    
    if not incident:
        return None
    
    if "root_cause" in payload:
        incident.root_cause = payload["root_cause"]
        incident.status = "resolved"
        incident.resolved_at = datetime.utcnow()
    
    if "confidence" in payload:
        incident.confidence = payload["confidence"]
        
    db.commit()
    return {"status": "updated", "incident_id": incident.incident_id, "root_cause": incident.root_cause}
