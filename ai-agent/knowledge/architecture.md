# Architecture Documentation
The Order Backend is a FastAPI service.
- **Database**: PostgreSQL 15, used for persistent storage of orders.
- **Cache**: Redis, used to cache order reads to improve latency.
- **Payment Gateway**: External API called synchronously during `POST /orders/{id}/process`.

If the external payment gateway times out (504), the order stays in 'created' state and must be retried later.
