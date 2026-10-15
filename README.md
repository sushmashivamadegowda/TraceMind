# AI-Driven SRE Incident Resolution System

This project demonstrates a complete, production-like microservice architecture with deliberate chaos injection, comprehensive observability, and an autonomous AI SRE agent that uses RAG (Retrieval-Augmented Generation) to investigate and resolve incidents.

## Architecture Overview

The system is entirely containerized via Docker Compose and consists of the following components:

1. **Order API**: A FastAPI backend (`localhost:8080`) that processes orders. It features a built-in Chaos Engineering module to deliberately inject failures.
2. **Prometheus**: Scrapes metrics from the API (CPU, Memory, DB connections, HTTP errors, Latency).
3. **Loki & Promtail**: Collects and stores structured JSON logs from the API.
4. **Grafana**: Visualizes metrics and logs.
5. **Alertmanager**: Evaluates Prometheus rules and fires webhooks when incidents occur.
6. **Incident Manager**: A separate FastAPI service (`localhost:8081`) backed by PostgreSQL. It receives webhooks from Alertmanager and tracks active incidents.
7. **AI SRE Agent**: A Python script (`ai-agent/agent.py`) that acts as an autonomous engineer. It uses an LLM ReAct loop to query logs, metrics, and a local ChromaDB RAG knowledge base to find root causes.

## How to Run

### 1. Start the Infrastructure
Navigate to the `order-backend` directory and spin up the Docker stack:
```bash
cd order-backend
docker-compose up -d --build
```
This starts the API, PostgreSQL, Prometheus, Alertmanager, Loki, Promtail, Grafana, and the Incident Manager.

### 2. Inject Chaos
The API exposes endpoints to simulate various production outages. For example, to simulate a database connection exhaustion:
```bash
curl -X POST "http://localhost:8080/chaos/database-timeout?enable=true"
```
Generate some traffic to trigger the incident:
```bash
for ($i=0; $i -lt 30; $i++) { 
    curl.exe -s -X POST http://localhost:8080/orders -H "Content-Type: application/json" -d '{\"customer_id\": \"cust_1\", \"items\": [{\"product_id\": \"prod_1\", \"quantity\": 1, \"price\": 10.0}]}'
}
```

### 3. Verify Alerting
Within 1 minute, Prometheus will detect the anomaly and trigger the `HighErrorRate` or `HighLatency` alert. 
You can view the active incident by querying the Incident Manager:
```bash
curl http://localhost:8081/incidents
```

### 4. Run the AI SRE Agent
Once an incident is active, unleash the AI Agent to investigate it:
```bash
cd ../ai-agent
pip install -r requirements.txt
$env:OPENAI_API_KEY="your-real-openai-key"
python agent.py
```
The agent will:
- Detect the open incident.
- Query its local RAG database (ChromaDB) for relevant runbooks.
- Query Prometheus and Loki to validate the symptoms against the runbook.
- Recommend a remediation strategy for human approval.
- Execute the remediation via the API and mark the incident resolved in PostgreSQL.

## Final Production Architecture Vision (Phase 12)

Eventually, this system is designed to evolve into a fully asynchronous, scalable platform that looks like this:

```text
                         ┌───────────────────┐
                         │ Developer         │
                         │ Dashboard         │
                         └─────────┬─────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │      FastAPI      │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Incident Manager  │
                         └─────────┬─────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │ Redis / Queue     │
                         └─────────┬─────────┘
                                   │
                                   ▼
                  ┌──────────────────────────────┐
                  │       AI INCIDENT AGENT      │
                  │                              │
                  │ Planner                      │
                  │ Reasoner                     │
                  │ Tool selection               │
                  │ Evidence collection          │
                  └──────────────┬───────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           │                     │                     │
           ▼                     ▼                     ▼
      Log Search            Metrics Query          Git Analysis
           │                     │                     │
           ▼                     ▼                     ▼
         Loki               Prometheus             GitHub
           │                     │
           └──────────────┬──────┘
                          ▼
                 ┌─────────────────┐
                 │ RAG / Memory    │
                 │ Vector DB       │
                 └────────┬────────┘
                          │
                          ▼
                  Root Cause Analysis
                          │
                          ▼
                  ┌───────────────┐
                  │ Human Review  │
                  └───────┬───────┘
                          │
                ┌─────────┼──────────┐
                ▼         ▼          ▼
             Restart   Rollback    Scale
```
