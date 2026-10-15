import pytest
from fastapi.testclient import TestClient
from main import app, CHAOS_STATE
import time
import threading

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_chaos_state():
    """Reset chaos state before each test to ensure test isolation"""
    for key in CHAOS_STATE:
        CHAOS_STATE[key] = False
    yield

def create_test_order():
    """Helper to dynamically create an order for tests needing a valid ID"""
    res = client.post("/orders", json={
        "customer_id": "cust_test",
        "items": [{"product_id": "p1", "quantity": 1, "price": 10.0}]
    })
    return res.json()["order_id"]

# ==========================================
# 1. Normal Production Business Logic Tests
# ==========================================

def test_create_order_success():
    """Test normal order creation without chaos"""
    response = client.post("/orders", json={
        "customer_id": "cust_123",
        "items": [{"product_id": "p1", "quantity": 1, "price": 10.0}]
    })
    assert response.status_code == 201
    data = response.json()
    assert "order_id" in data
    assert data["status"] == "created"

def test_create_order_missing_fields():
    """Production Edge Case: 422 Unprocessable Entity on missing required fields"""
    response = client.post("/orders", json={
        "customer_id": "cust_123"
        # missing 'items' array
    })
    assert response.status_code == 422

def test_create_order_invalid_types():
    """Production Edge Case: 422 on invalid data types"""
    response = client.post("/orders", json={
        "customer_id": "cust_123",
        "items": [{"product_id": "p1", "quantity": "not-a-number", "price": 10.0}]
    })
    assert response.status_code == 422

def test_get_order_success():
    """Test reading an order from cache/db"""
    order_id = create_test_order()
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["order_id"] == order_id

def test_process_order_success():
    """Test asynchronous order processing endpoint"""
    order_id = create_test_order()
    response = client.post(f"/orders/{order_id}/process")
    assert response.status_code == 200
    assert response.json()["message"] == "Order is now processing"

# ==========================================
# 2. Concurrency & Load Simulation
# ==========================================

def test_burst_traffic_simulation():
    """Mimics a production burst of traffic to ensure no state corruption"""
    responses = []
    
    def make_request():
        res = client.post("/orders", json={
            "customer_id": "cust_burst",
            "items": [{"product_id": "p1", "quantity": 2, "price": 5.0}]
        })
        responses.append(res.status_code)
        
    threads = []
    for _ in range(20):
        t = threading.Thread(target=make_request)
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # All 20 requests should succeed simultaneously
    assert len(responses) == 20
    assert all(status == 201 for status in responses)

# ==========================================
# 3. Chaos Engineering Tests
# ==========================================

def test_chaos_database_timeout():
    """Test that the database-timeout chaos flag correctly triggers 500s"""
    client.post("/chaos/database-timeout?enable=true")
    
    response = client.post("/orders", json={
        "customer_id": "cust_123",
        "items": []
    })
    assert response.status_code == 500
    assert "database timeout" in response.json()["detail"].lower()

def test_chaos_redis_failure():
    """Test that Redis failure handles cache misses gracefully"""
    order_id = create_test_order()
    client.post("/chaos/redis-failure?enable=true")
    
    start_time = time.time()
    response = client.get(f"/orders/{order_id}")
    duration = time.time() - start_time
    
    assert response.status_code == 200 
    assert duration >= 0.45  # Asserts the fallback latency is actually applied (buffer for CI)

def test_chaos_bad_deployment():
    """Test bad deployment TypeError crash simulation"""
    client.post("/chaos/bad-deployment?enable=true")
    
    response = client.post("/orders", json={"customer_id": "c1", "items": []})
    assert response.status_code == 500
    assert "internal error" in response.json()["detail"].lower()

def test_chaos_external_api_failure():
    """Test payment gateway 504 timeout simulation"""
    order_id = create_test_order()
    client.post("/chaos/external-api-failure?enable=true")
    
    response = client.post(f"/orders/{order_id}/process")
    assert response.status_code == 504
    assert "timeout" in response.json()["detail"].lower()

def test_chaos_n_plus_one():
    """Test N+1 query simulation latency injection"""
    order_id = create_test_order()
    client.post("/chaos/n-plus-one?enable=true")
    
    start_time = time.time()
    response = client.get(f"/orders/{order_id}")
    duration = time.time() - start_time
    
    assert response.status_code == 200
    assert duration >= 0.45  # N+1 adds 0.5s to latency (buffer for CI)

# ==========================================
# 4. Remediation & Telemetry Tests
# ==========================================

def test_remediation_restart_service():
    """Test that the remediation endpoint successfully fixes chaos state"""
    client.post("/chaos/database-timeout?enable=true")
    client.post("/remediation/restart_service")
    
    response = client.post("/orders", json={"customer_id": "c1", "items": []})
    assert response.status_code == 201

def test_metrics_endpoint_is_exposed():
    """Test that Prometheus metrics are correctly exported and updated"""
    # Trigger an order to increment metrics
    client.post("/orders", json={"customer_id": "m1", "items": []})
    
    response = client.get("/metrics")
    assert response.status_code == 200
    metrics_data = response.text
    
    # Assert critical prometheus counters are present
    assert "http_requests_total" in metrics_data
    assert "http_request_duration_seconds" in metrics_data
    assert "database_connections" in metrics_data
