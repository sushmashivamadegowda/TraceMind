# Simple Order Backend

This is a simple order backend application built with FastAPI. It includes structured JSON logging and Prometheus metrics, ready for testing deliberate failure injection.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## Endpoints

- `POST /orders`: Create a new order
- `GET /orders/{order_id}`: Retrieve an order
- `POST /orders/{order_id}/process`: Process an order
- `GET /metrics`: Prometheus metrics
- `GET /health`: Health check
