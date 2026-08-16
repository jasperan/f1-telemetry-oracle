# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
* **In-database ONNX scoring is real**: `/predict/tire-life` and `/predict/pit-window` now score with `PREDICTION()` over `TIRE_GRIP_MODEL` / `TIRE_LAPS_MODEL` inside Oracle (heuristic fallback when models aren't loaded). Models are now trained as single-output regressors (Oracle 23ai rejects multi-output ONNX) with explicit `{"input": {"X": [...]}}` metadata.
* **In-database text embeddings + RAG**: loads the Oracle-augmented all-MiniLM-L12-v2 embedding model, seeds a `race_documents` knowledge base (setup guides, strategy, circuit guides, history) embedded via `VECTOR_EMBEDDING()` in SQL, and adds semantic document retrieval to the RAG pipeline (`scripts/load_onnx_models.py`, `scripts/seed_race_documents.py`).
* **Agentic race engineer**: the LLM now plans its own retrieval through 8 database tools (`api/services/agent.py`) — laps, telemetry, comparison, tire ONNX, pit window, vector search, semantic docs, setup — with classic RAG fallback. Ollama client gained native `tools` support.
* **Retrieval transparency**: every chat response includes a `trace` (path, tools called, iterations, per-source counts, per-stage latency) rendered in the chat UI.
* **Driving twin**: `/api/compare/driving-twin` matches a sim lap to the real driver you most resemble, per sector, via per-sector telemetry embeddings in `lap_sector_embeddings` scored by Oracle AI Vector Search.
* **Monte Carlo strategy simulator**: `/api/predict/strategy-sim` races thousands of simulated races per pit plan (in-DB tire physics + stochastic weather/SC) and ranks strategies by win probability; wired into the Strategy Advisor panel.
* New schema objects: `race_documents`, `lap_sector_embeddings` (plus supporting indexes).

### Fixed
* Chat WebSocket used a nonexistent `websocket.app` — every WS message errored. Now reads the app from `websocket.scope["app"]`.
* Sim-vs-Real panel called `/sim-vs-real?lap=` instead of the API's `lap_id` param.
* Strategy Advisor sent `lap_id` in request bodies the API doesn't accept and expected a list-shaped pit-window response; now uses the real contracts.
* ONNX loader metadata (inputColumns/outputColumns) was rejected by 23ai builds — replaced with the tensor-name input mapping.
* Integration test DSN is now overridable via `ORACLE_TEST_DSN/USER/PASSWORD`; `test_spatial` no longer hardcodes a foreign repo path.

## [0.3.0] - 2021-09-04
### Added
* Duplicate packets file with cleaned up names, `m_` removed and `tyres` is now `tyre`
