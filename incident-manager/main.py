from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import init_db, get_db
from serve import incident_service

# Initialize DB tables (all db setup hidden inside database.py)
init_db()

app = FastAPI(title="Incident Manager")

@app.post("/webhook")
async def prometheus_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    return incident_service.process_webhook_alerts(payload, db)
    
@app.get("/incidents")
def get_incidents(db: Session = Depends(get_db)):
    return incident_service.get_all_incidents(db)

@app.patch("/incidents/{incident_id}")
async def update_incident(incident_id: str, request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    result = incident_service.update_incident_details(incident_id, payload, db)
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result
