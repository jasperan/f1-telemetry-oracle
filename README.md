# F1 Telemetry Oracle -- AI Race Engineer

AI-powered F1 race engineer that compares your sim telemetry to real F1 data, backed by **Oracle Database 23ai Free** with Vector Search, Spatial, JSON Duality Views, and in-database ONNX models.

## Architecture

```
DATA SOURCES                              ORACLE DATABASE 23ai FREE
                                           +---------------------------------+
  F1 24/25 Game (UDP) ----+                | JSON Relational Duality Views   |
  OpenF1 API (2023-25) ---+--> Collectors  | AI Vector Search (384-dim)      |
  Ergast API (1950-25) ---+    & Normalizer| In-DB ONNX Models               |
                                     |     | Oracle Spatial (track geometry)  |
                                     v     +---------------------------------+
                               FastAPI Backend (REST + WebSocket)
                                     |
                                     v
                               Next.js 14 Dashboard
                               +--------------------+--------------------+
                               | Live Telemetry     | AI Race Engineer   |
                               | (speed, throttle,  | Chat (RAG-powered) |
                               | brake, steering)   |                    |
                               +--------------------+--------------------+
                               | 3D Track Map       | Sim vs Real        |
                               | (Three.js)         | Comparison         |
                               +--------------------+--------------------+
                               | Strategy Advisor   | Historical         |
                               | (tire + pit ONNX)  | Explorer           |
                               +--------------------+--------------------+
```

## Features

| Panel | Description |
|-------|-------------|
| **Live Telemetry** | Real-time speed, throttle, brake, steering via WebSocket from F1 24/25 UDP feed |
| **AI Race Engineer** | Ask questions about lap performance, strategy, and history. RAG-powered with SQL + vector search + graph retrieval |
| **3D Track Map** | Circuit visualization with Three.js -- car positions and telemetry heatmap overlays |
| **Sim vs Real** | Overlay your F1 game telemetry against real-world F1 data, aligned by track distance |
| **Strategy Advisor** | Tire degradation prediction and optimal pit window using in-database ONNX models |
| **Historical Explorer** | Natural language search over 75 years of F1 history from Ergast + OpenF1 |

## Oracle 23ai Features Used

| Feature | Usage |
|---------|-------|
| **JSON Relational Duality Views** | Write telemetry as JSON documents, query relationally -- zero impedance mismatch |
| **AI Vector Search** | 384-dim lap embeddings with cosine distance for semantic similarity search |
| **In-Database ONNX** | Tire degradation predictor and pit window optimizer running inside the DB |
| **Oracle Spatial** | Track geometry (SDO_GEOMETRY), haversine distance queries, circuit coordinate storage |
| **JSON Document Store** | Weather data, car setup configs, and race event payloads stored as native JSON |

## Quickstart

<!-- one-command-install -->
> **One-command install**: clone, configure, and run in a single step:
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/jasperan/f1-telemetry-oracle/feat/race-engineer-ai/install.sh | bash
> ```
>
> <details><summary>Advanced options</summary>
>
> Override install location:
> ```bash
> PROJECT_DIR=/opt/myapp curl -fsSL https://raw.githubusercontent.com/jasperan/f1-telemetry-oracle/feat/race-engineer-ai/install.sh | bash
> ```
>
> Or install manually:
> ```bash
> git clone https://github.com/jasperan/f1-telemetry-oracle.git
> cd f1-telemetry-oracle
> # See below for setup instructions
> ```
> </details>


```bash
# Clone and start everything
git clone https://github.com/jasperan/f1-telemetry-oracle.git
cd f1-telemetry-oracle
docker compose up --build

# Services:
#   Frontend:  http://localhost:3100
#   API:       http://localhost:8100
#   API docs:  http://localhost:8100/docs  (Swagger UI)
#   Oracle:    localhost:1525/FREEPDB1
```

### Seed Historical Data

```bash
# Seed circuit geometry and spatial data
docker compose exec api python scripts/seed_circuits.py

# Load ONNX models into Oracle
docker compose exec api python scripts/load_onnx_models.py
```

### Connect F1 24/25 Game

1. In game settings, set UDP telemetry to `<your-machine-ip>:20777`
2. The UDP collector starts automatically with `docker compose up`
3. Live telemetry appears on the dashboard in real-time

## Development Setup

### Prerequisites

- Docker + Docker Compose
- Python 3.12+ (uv recommended)
- Node.js 20+
- Ollama with `qwen3.5:35b-a3b` (for AI race engineer)

### Backend

```bash
# Install Python dependencies (uv manages the project venv from uv.lock)
pip install uv
uv sync --extra dev

# Start Oracle 23ai Free
docker compose up oracle-26ai -d

# Apply schema
python -c "
import asyncio
from api.services.oracle import OraclePool
from pathlib import Path

async def main():
    pool = OraclePool(dsn='localhost:1525/FREEPDB1', user='f1app', password='f1app')
    await pool.open()
    await pool.execute_script(Path('api/db/schema.sql').read_text())
    await pool.close()

asyncio.run(main())
"

# Run API server
uvicorn api.main:app --reload --host 0.0.0.0 --port 8100
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

### Ollama (AI Race Engineer)

```bash
ollama pull qwen3.5:35b-a3b
ollama serve   # or use the Ollama container in docker-compose
```

## Testing

```bash
# Unit tests (fast, no external deps)
uv run pytest tests/unit/ -v

# Integration tests (requires Oracle container on port 1525)
uv run pytest tests/integration/ -v -m integration

# Frontend build verification
cd frontend && npm run build

# E2E tests (requires full stack running)
cd tests/e2e && npm install && npx playwright test
```

## API Reference

Interactive API docs are available at `http://localhost:8100/docs` (Swagger UI) when the API server is running.

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/circuits` | GET | List all circuits with track metadata |
| `/api/drivers` | GET | List drivers (filterable by nationality, sim player) |
| `/api/sessions` | GET | List sessions (filterable by source, circuit, season) |
| `/api/sessions/{id}` | GET | Session detail |
| `/api/laps` | GET | List laps (filterable by session, driver) |
| `/api/laps/{id}` | GET | Lap detail with sector times |
| `/api/laps/{id}/telemetry` | GET | Paginated telemetry frames (cursor-based) |
| `/api/laps/{id}/similar` | GET | Vector similarity search for similar laps |
| `/api/compare/laps?ids=a,b` | GET | Compare two laps with distance-aligned telemetry deltas |
| `/api/compare/sim-vs-real` | GET | Auto-match sim lap to best real-world lap and compare |
| `/api/predict/tire-life` | POST | ONNX tire degradation prediction |
| `/api/predict/pit-window` | POST | ONNX optimal pit window prediction |
| `/api/chat/message` | POST | RAG-powered AI race engineer chat |
| `/ws/live` | WebSocket | Real-time telemetry stream |
| `/ws/chat` | WebSocket | Streaming chat responses |
| `/health` | GET | Health check |

## Project Structure

```
f1-telemetry-oracle/
├── api/                        # FastAPI backend
│   ├── main.py                 # App factory with lifespan management
│   ├── config.py               # Pydantic settings (Oracle, Ollama, APIs)
│   ├── routers/                # Endpoint modules
│   │   ├── circuits.py         # Circuit CRUD
│   │   ├── drivers.py          # Driver CRUD
│   │   ├── sessions.py         # Session listing with filters
│   │   ├── laps.py             # Laps, telemetry, vector search
│   │   ├── compare.py          # Lap comparison, sim-vs-real
│   │   ├── predict.py          # Tire life + pit window (ONNX)
│   │   ├── chat.py             # RAG chat endpoint
│   │   └── ws.py               # WebSocket live telemetry + chat
│   ├── services/               # Business logic
│   │   ├── oracle.py           # Async connection pool
│   │   ├── ollama.py           # LLM client
│   │   └── rag.py              # Query understanding + context assembly
│   ├── models/                 # Pydantic schemas
│   │   └── schemas.py          # All request/response models
│   └── db/                     # Database DDL + shared SQL fragments
│       ├── columns.py          # Shared lap/frame column lists
│       ├── schema.sql          # Core 10-table schema
│       ├── vector.sql          # Vector search index setup
│       ├── spatial.sql         # Spatial geometry + indexes
│       └── duality_views.sql   # JSON Relational Duality Views
├── collectors/                 # Data ingestion pipelines
│   ├── normalizer.py           # Unified NormalizedLap/NormalizedFrame
│   ├── f1_udp/                 # F1 24 async UDP listener + packet decoder
│   ├── openf1/                 # Live polling + batch backfill
│   └── ergast/                 # Historical bulk collector
├── frontend/                   # Next.js 14 dashboard
│   ├── app/                    # Pages + layout (dark racing theme)
│   ├── components/             # 6 dashboard panels
│   └── lib/                    # WebSocket hook, Zustand store
├── scripts/                    # Seed + model loading utilities
├── tests/
│   ├── unit/                   # Fast tests, no external deps
│   ├── integration/            # Oracle container round-trip tests
│   ├── e2e/                    # Playwright dashboard E2E tests
│   └── fixtures/               # SQL seed data
├── .github/workflows/ci.yml   # GitHub Actions CI pipeline
├── docker-compose.yml          # Full stack: Oracle + Ollama + API + Frontend
└── pyproject.toml              # Python project config (hatch + ruff + pytest)
```

## Tech Stack

- **Database**: Oracle Database 23ai Free (Vector Search, Spatial, JSON Duality Views, ONNX)
- **Backend**: FastAPI, oracledb (async thin mode), Pydantic v2
- **Frontend**: Next.js 14, React 18, Recharts, Three.js (react-three-fiber), Zustand, Tailwind CSS
- **AI/LLM**: Ollama (Qwen 3.5 35B-A3B), RAG with vector + SQL + graph retrieval
- **Data Sources**: F1 24/25 UDP telemetry, OpenF1 API, Ergast API
- **Testing**: pytest + pytest-asyncio, Playwright, Vitest
- **CI/CD**: GitHub Actions (lint, test, build, integration, E2E)

## Credits

The original UDP packet deserialization is based on work by [chrishannam/Telemetry-F1-2021](https://github.com/chrishannam/Telemetry-F1-2021) and the [CodeMasters F1 2021 UDP specification](https://forums.codemasters.com/topic/80231-f1-2021-udp-specification/).

## License

MIT
