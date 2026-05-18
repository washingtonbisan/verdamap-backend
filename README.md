# VerdaMap Backend

FastAPI backend for NDVI vegetation analysis using Sentinel-2 satellite imagery.

## Stack

- **FastAPI** — async Python web framework
- **PostgreSQL** — production database (via asyncpg)
- **Sentinel Hub** — Sentinel-2 satellite imagery API
- **SQLAlchemy 2** — async ORM

## Prerequisites

- Python 3.11+
- Docker (for local PostgreSQL)
- A [Sentinel Hub](https://www.sentinel-hub.com/) account (free tier is enough)

---

## Local Setup

### 1. Clone and enter the backend directory

```bash
cd VerdaMap/backend
```

### 2. Create a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Where to get it |
|---|---|
| `SENTINELHUB_CLIENT_ID` | [Sentinel Hub Dashboard](https://apps.sentinel-hub.com/dashboard/#/account/settings) → OAuth clients → Create new |
| `SENTINELHUB_CLIENT_SECRET` | Same page |
| `DATABASE_URL` | Leave as-is for local Docker setup |

### 5. Start PostgreSQL with Docker

```bash
docker compose up -d
```

This starts a PostgreSQL 16 instance on `localhost:5432`.  
Tables are created automatically when the API starts.

### 6. Run the development server

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now running at **http://localhost:8000**

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analyze` | Run NDVI analysis on a polygon |
| `GET` | `/api/history` | Get the 50 most recent analyses |
| `GET` | `/api/analysis/{id}` | Get a single analysis by ID |
| `GET` | `/health` | Liveness check |

### POST /api/analyze — Request body

```json
{
  "polygon": [
    [lon, lat],
    [lon, lat],
    [lon, lat],
    [lon, lat]
  ],
  "date_from": "2024-01-01",
  "date_to": "2024-02-01"
}
```

---

## Production Deployment

1. Set `DATABASE_URL` to your production PostgreSQL connection string (Supabase, Neon, Railway, etc.)
2. Set `API_BASE_URL` to your backend's public URL (e.g. `https://api.yourdomain.com`)
3. Set `ALLOWED_ORIGINS` to your frontend's public URL
4. Run with: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

For containerized deployments, a `Dockerfile` can be added — the app has no special requirements beyond Python 3.11+ and the packages in `requirements.txt`.
