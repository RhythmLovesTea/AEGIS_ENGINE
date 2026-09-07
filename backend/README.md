# AEGIS-Marine — Backend Services

Core Python FastAPI and Celery orchestration platform for oil spill detection, hindcasting, and vessel attribution.

## Architecture
- `app/`: FastAPI application, HTTP routers, Pydantic schemas, and security/RBAC middleware.
- `core/`: Application settings, Celery application instance, and database connection pools.
- `services/`: Specialized computational tier engines (Tiers 1–4, Explainability, Dossier, Data Adapters).
- `workers/`: Celery asynchronous worker tasks.
