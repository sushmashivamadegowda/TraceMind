# Runbook: Redis Cache Failure
**Symptoms**: Cache misses spike to 100%, increased API latency fetching orders.
**Root Cause**: Redis node went down or ran out of memory (OOM).
**Resolution Steps**:
1. API is designed to fall back to the PostgreSQL database gracefully, so availability should not be fully compromised, just degraded latency.
2. Check Redis memory usage metrics.
3. Restart Redis container to flush memory if OOM.
