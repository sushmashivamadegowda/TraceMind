import requests
import time

BASE_URL = "http://localhost:8080"
print("Starting E2E Testing...")

# 1. Test Happy Path: Create Order
print("\n[1] Testing Order Creation (Happy Path)...")
payload = {
    "customer_id": "cust_tester",
    "items": [{"product_id": "prod_1", "quantity": 2, "price": 15.5}]
}
resp = requests.post(f"{BASE_URL}/orders", json=payload)
if resp.status_code == 201:
    order_data = resp.json()
    order_id = order_data["order_id"]
    print(f"Success! Created order {order_id} with total {order_data['total_amount']}")
else:
    print(f"Failed: {resp.status_code} {resp.text}")
    exit(1)

# 2. Test Happy Path: Get Order
print("\n[2] Testing Order Fetch...")
resp = requests.get(f"{BASE_URL}/orders/{order_id}")
if resp.status_code == 200:
    print(f"Success! Fetched order {order_id}. Status: {resp.json()['status']}")
else:
    print(f"Failed: {resp.status_code} {resp.text}")

# 3. Test Edge Case: Not Found
print("\n[3] Testing Order Not Found...")
resp = requests.get(f"{BASE_URL}/orders/invalid_order_id")
if resp.status_code == 404:
    print("Success! Properly returned 404 for missing order.")
else:
    print(f"Failed: Expected 404, got {resp.status_code}")

# 4. Test Fault Injection: Database Timeout
print("\n[4] Enabling Chaos: Database Timeout...")
resp = requests.post(f"{BASE_URL}/chaos/database-timeout?enable=true")
if resp.status_code == 200:
    print("Chaos enabled.")
else:
    print(f"Failed to enable chaos: {resp.status_code}")

print("    Trying to create an order under DB Timeout conditions (should fail)...")
try:
    resp = requests.post(f"{BASE_URL}/orders", json=payload, timeout=6)
    if resp.status_code == 500:
        print(f"Success! System correctly failed with 500 Internal Error as expected. ({resp.json()})")
    else:
        print(f"Failed: Expected 500, got {resp.status_code}")
except requests.exceptions.Timeout:
    print("Success! Request timed out, simulating severe DB lock.")

# 5. Test Remediation
print("\n[5] Executing Remediation (Restart Service)...")
resp = requests.post(f"{BASE_URL}/remediation/restart_service")
if resp.status_code == 200:
    print("Remediation executed successfully.")
else:
    print(f"Remediation failed: {resp.status_code}")

print("    Verifying system recovery...")
resp = requests.post(f"{BASE_URL}/orders", json=payload)
if resp.status_code == 201:
    print(f"Success! System recovered and created order {resp.json()['order_id']}")
else:
    print(f"Failed: System did not recover. Status: {resp.status_code}")

print("\nAll tests completed!")
