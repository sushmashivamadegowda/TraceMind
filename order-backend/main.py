import logging.config
import uuid
import contextvars
from datetime import datetime
import random
import time
from typing import List
import asyncio
import psutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pythonjsonlogger import jsonlogger

# Context variables for logging
request_id_ctx_var = contextvars.ContextVar("request_id", default="")
endpoint_ctx_var = contextvars.ContextVar("endpoint", default="")

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            log_record['timestamp'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
        if 'asctime' in log_record:
            del log_record['asctime']
        if not log_record.get('level'):
            log_record['level'] = record.levelname
        if 'levelname' in log_record:
            del log_record['levelname']
        log_record['service'] = 'order-service'
        trace_id = request_id_ctx_var.get()
        if trace_id: log_record['trace_id'] = trace_id
        endpoint = endpoint_ctx_var.get()
        if endpoint: log_record['endpoint'] = endpoint
        if 'name' in log_record: del log_record['name']

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "main.CustomJsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "app.log",
            "formatter": "json",
        }
    },
    "loggers": {
        "order_backend": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    }
}
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("order_backend")

# --- Metrics Setup ---
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "http_status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"])
ORDER_COUNT = Counter("orders_total", "Total number of orders created", ["status"])
HTTP_ERRORS = Counter("http_errors_total", "Total HTTP errors", ["method", "endpoint", "error_type"])
DB_CONNECTIONS = Gauge("database_connections", "Number of database connections", ["status"])
CPU_USAGE = Gauge("cpu_usage", "CPU usage percentage")
MEMORY_USAGE = Gauge("memory_usage", "Memory usage in bytes")
REDIS_OPS = Counter("redis_operations", "Total Redis operations", ["operation"])
CACHE_MISSES = Counter("cache_misses_total", "Total cache misses")

DB_CONNECTIONS.labels(status="active").set(0)
DB_CONNECTIONS.labels(status="idle").set(10)

# --- Chaos State ---
CHAOS_STATE = {
    "database-timeout": False,
    "redis-failure": False,
    "bad-deployment": False,
    "external-api-failure": False,
    "n-plus-one": False,
}

async def update_system_metrics():
    while True:
        try:
            CPU_USAGE.set(psutil.cpu_percent(interval=None))
            MEMORY_USAGE.set(psutil.virtual_memory().used)
        except Exception:
            pass
        await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(update_system_metrics())
    yield
    task.cancel()

app = FastAPI(title="Order Backend", lifespan=lifespan)

@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    method = request.method
    endpoint = request.url.path
    trace_id = str(uuid.uuid4())
    request_id_ctx_var.set(trace_id)
    endpoint_ctx_var.set(endpoint)
    
    if endpoint == "/metrics":
        return await call_next(request)
        
    start_time = time.time()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        if status_code >= 400:
            HTTP_ERRORS.labels(method=method, endpoint=endpoint, error_type=str(status_code)).inc()
    except Exception as e:
        HTTP_ERRORS.labels(method=method, endpoint=endpoint, error_type="exception").inc()
        logger.error("Internal Server Error", extra={"error": str(e), "status_code": 500})
        raise e
    finally:
        latency = time.time() - start_time
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)
        
    return response

# --- Models ---
class OrderItem(BaseModel):
    product_id: str
    quantity: int
    price: float

class OrderCreate(BaseModel):
    customer_id: str
    items: List[OrderItem]

class Order(OrderCreate):
    order_id: str
    status: str
    total_amount: float

orders_db = {}

# --- Chaos Endpoint ---
@app.post("/chaos/{scenario}")
async def toggle_chaos(scenario: str, enable: bool = True):
    if scenario in CHAOS_STATE:
        CHAOS_STATE[scenario] = enable
        logger.warning(f"Chaos scenario toggled", extra={"scenario": scenario, "enabled": enable})
        return {"scenario": scenario, "enabled": enable}
    raise HTTPException(status_code=404, detail="Scenario not found")

@app.get("/users")
async def get_users():
    return {"status": "ok", "users": [{"id": 1, "name": "Alice"}]}

# --- Endpoints ---
@app.post("/orders", response_model=Order, status_code=201)
async def create_order(order_create: OrderCreate):
    logger.info("Creating order", extra={"customer_id": order_create.customer_id})
    
    # 3. Bad Deployment Simulation
    if CHAOS_STATE["bad-deployment"]:
        logger.error("Uncaught TypeError in orders router", extra={"status_code": 500, "error": "TypeError: 'NoneType' object is not subscriptable"})
        raise HTTPException(status_code=500, detail="Internal error")

    # DB Connection Tracking
    DB_CONNECTIONS.labels(status="active").inc()
    DB_CONNECTIONS.labels(status="idle").dec()
    
    try:
        # 1. DB Connection Exhaustion Simulation
        if CHAOS_STATE["database-timeout"]:
            DB_CONNECTIONS.labels(status="active").inc(90)
            DB_CONNECTIONS.labels(status="idle").dec(90)
            try:
                await asyncio.sleep(4.0)
            finally:
                DB_CONNECTIONS.labels(status="active").dec(90)
                DB_CONNECTIONS.labels(status="idle").inc(90)
            logger.error("database timeout", extra={"status_code": 500, "error": "database timeout"})
            raise HTTPException(status_code=500, detail="database timeout")
        
        await asyncio.sleep(0.05)
        
        total_amount = sum(item.quantity * item.price for item in order_create.items)
        order_id = f"ord_{random.randint(1000, 9999)}"
        
        order = Order(order_id=order_id, customer_id=order_create.customer_id, items=order_create.items, status="created", total_amount=total_amount)
        orders_db[order_id] = order
    finally:
        DB_CONNECTIONS.labels(status="active").dec()
        DB_CONNECTIONS.labels(status="idle").inc()
    
    # Redis Simulation
    if CHAOS_STATE["redis-failure"]:
        await asyncio.sleep(1.0)
        CACHE_MISSES.inc()
        logger.warning("Redis connection failed", extra={"status_code": 201})
    else:
        REDIS_OPS.labels(operation="SET").inc()
        
    ORDER_COUNT.labels(status="created").inc()
    logger.info("Order created successfully", extra={"order_id": order_id, "total_amount": total_amount})
    return order

@app.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str):
    logger.info("Fetching order", extra={"order_id": order_id})
    
    if CHAOS_STATE["redis-failure"]:
        await asyncio.sleep(0.5)
        CACHE_MISSES.inc()
        logger.warning("Redis connection failed during GET", extra={"status_code": 200})
    else:
        REDIS_OPS.labels(operation="GET").inc()
    
    # 5. N+1 Simulation
    if CHAOS_STATE["n-plus-one"]:
        for _ in range(50):
            DB_CONNECTIONS.labels(status="active").inc()
            try:
                await asyncio.sleep(0.01) # lots of queries
            finally:
                DB_CONNECTIONS.labels(status="active").dec()
    
    order = orders_db.get(order_id)
    if not order:
        logger.warning("Order not found", extra={"order_id": order_id, "status_code": 404})
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.post("/orders/{order_id}/process")
async def process_order(order_id: str):
    logger.info("Processing order", extra={"order_id": order_id})
    
    order = orders_db.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # 4. External API Failure Simulation
    if CHAOS_STATE["external-api-failure"]:
        logger.info("Calling external payment service...")
        await asyncio.sleep(5.0)
        logger.error("Payment service timeout", extra={"status_code": 504, "error": "upstream timeout"})
        raise HTTPException(status_code=504, detail="Payment gateway timeout")
        
    DB_CONNECTIONS.labels(status="active").inc()
    DB_CONNECTIONS.labels(status="idle").dec()
    try:
        await asyncio.sleep(0.1) 
        order.status = "processing"
        orders_db[order_id] = order
    finally:
        DB_CONNECTIONS.labels(status="active").dec()
        DB_CONNECTIONS.labels(status="idle").inc()
    
    logger.info("Order processed", extra={"order_id": order_id, "status": "processing"})
    ORDER_COUNT.labels(status="processing").inc()
    return {"message": "Order is now processing", "order_id": order_id}

# --- Remediation Endpoints ---
@app.post("/remediation/{action}")
async def execute_remediation(action: str):
    logger.info("Executing remediation", extra={"action": action})
    if action == "restart_service":
        CHAOS_STATE["database-timeout"] = False
        CHAOS_STATE["redis-failure"] = False
        return {"status": "success", "message": "Service restarted and pool flushed."}
    elif action == "rollback_deployment":
        CHAOS_STATE["bad-deployment"] = False
        return {"status": "success", "message": "Deployment rolled back."}
    elif action == "disable_feature_flag":
        CHAOS_STATE["n-plus-one"] = False
        return {"status": "success", "message": "Feature flag disabled."}
    elif action == "clear_cache":
        CHAOS_STATE["redis-failure"] = False
        return {"status": "success", "message": "Cache cleared."}
    
    raise HTTPException(status_code=404, detail="Unknown remediation action")

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health():
    return {"status": "ok"}
