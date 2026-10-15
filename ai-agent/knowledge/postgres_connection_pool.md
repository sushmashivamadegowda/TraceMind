# Runbook: PostgreSQL Connection Exhaustion
**Symptoms**: High 500 error rate, latency spikes, DB connections approaching 100%. "database timeout" in logs.
**Root Cause**: Connections are not being released back to the pool, or traffic spiked beyond pool capacity.
**Resolution Steps**:
1. Check if it's a connection leak (idle connections = 0, active = max).
2. If leak, restart the API service immediately to clear the pool.
3. If traffic spike, scale up the API replicas or increase max connections in `database.yaml`.

**Previous Incident Notes (INC-991)**: Last time this happened, it was an N+1 query issue in the `/orders` endpoint locking connections. Check Prometheus metric `database_connections{status="active"}`. Do not just increase the pool size blindly without checking for leaks!
