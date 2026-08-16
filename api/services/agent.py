"""Agentic race engineer — tool-calling LLM over the F1 database.

Upgrades the classic intent->fixed-SQL RAG pipeline: the LLM (Qwen via
Ollama native /api/chat) is given a set of database tools and plans its
own multi-hop retrieval. It calls tools, receives results, and iterates
until it can answer — so arbitrary questions ("should I run mediums in a
35°C race?") work, not just a fixed set of intents.

Every tool executes against the same Oracle pool, and the tire
predictions reuse the in-database ONNX scoring path, so the agent's
numbers are the database's numbers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from api.db.columns import LAP_COLUMNS as _LAP_COLUMNS
from api.services import strategy
from api.services.rag import DOC_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 6
MAX_TOOL_RESULT_ROWS = 25

SYSTEM_PROMPT = (
    "You are an expert F1 race engineer AI assistant working as an agent. "
    "You have access to database tools that query real telemetry, lap times, "
    "tire strategy, and race knowledge. Plan your retrieval: call the tools "
    "you need, wait for results, and use the numbers to answer precisely. "
    "Prefer query_laps with filters over generic queries. Use "
    "predict_tire_life / predict_pit_window for strategy questions and "
    "search_documents for conceptual questions (setup, racecraft, history). "
    "Quote specific numbers from tool results. Be concise but thorough, use "
    "F1 terminology, and say honestly when the data does not support a claim."
)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI-style schema, consumed by Ollama /api/chat)
# ---------------------------------------------------------------------------
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_laps",
            "description": "Search laps by driver, circuit, season or session type. Returns lap times, sector times, tire compound, age and position.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "driver": {"type": "string", "description": "Driver code (VER) or name (max verstappen)"},
                    "circuit": {"type": "string", "description": "Circuit name, e.g. monza or silverstone"},
                    "season": {"type": "integer", "description": "Season year, e.g. 2024"},
                    "session_type": {"type": "string", "description": "race, qualifying, practice, etc."},
                    "limit": {"type": "integer", "description": "Max rows (default 10)", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_telemetry",
            "description": "Fetch telemetry frames (speed, throttle, brake, steering, gear, rpm, drs) for a lap, ordered by track distance.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "lap_id": {"type": "string", "description": "Lap identifier, e.g. lap_ver_1"},
                    "limit": {"type": "integer", "description": "Max frames (default 200)", "default": 200},
                },
                "required": ["lap_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_laps",
            "description": "Compare two laps: lap/sector times plus distance-aligned telemetry deltas. Use to find where time is gained or lost.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "lap_id_a": {"type": "string", "description": "First lap id (e.g. the sim player's)"},
                    "lap_id_b": {"type": "string", "description": "Second lap id"},
                },
                "required": ["lap_id_a", "lap_id_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_tire_life",
            "description": "Predict remaining tire life and grip for a compound given age, track temperature and fuel. Uses an in-database ONNX model.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "tire_compound": {"type": "string", "description": "SOFT, MEDIUM, HARD, INTER or WET"},
                    "tire_age_laps": {"type": "integer", "description": "Laps on the current set"},
                    "track_temp_c": {"type": "number", "description": "Track temperature in °C (default 30)"},
                    "fuel_load_kg": {"type": "number", "description": "Fuel load in kg (default 50)"},
                },
                "required": ["tire_compound", "tire_age_laps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_pit_window",
            "description": "Recommend the optimal pit lap, follow-on compound, and undercut/overcut viability given race state.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "current_lap": {"type": "integer", "description": "Current race lap"},
                    "total_laps": {"type": "integer", "description": "Total race length"},
                    "tire_compound": {"type": "string", "description": "Current compound"},
                    "tire_age_laps": {"type": "integer", "description": "Current tire age in laps"},
                    "gap_ahead_ms": {"type": "integer", "description": "Gap to car ahead in ms"},
                    "gap_behind_ms": {"type": "integer", "description": "Gap to car behind in ms"},
                },
                "required": ["current_lap", "total_laps", "tire_compound", "tire_age_laps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vector_search_laps",
            "description": "Find laps most similar to the sim player's latest lap using Oracle AI Vector Search on 384-dim lap embeddings.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "top_k": {"type": "integer", "description": "Number of similar laps (default 5)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Semantic search over the race-engineering knowledge base (setup guides, strategy notes, circuit guides, history) using in-database embeddings.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text question or topic"},
                    "top_k": {"type": "integer", "description": "Max docs (default 3)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_setup",
            "description": "Fetch the car setup used by a driver in a session (wing, camber, ride height, differential, etc.).",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session id"},
                    "driver_code": {"type": "string", "description": "Driver code, e.g. VER"},
                    "limit": {"type": "integer", "description": "Max rows (default 3)"},
                },
                "required": [],
            },
        },
    },
]

_TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


@dataclass
class AgentResult:
    """Outcome of an agentic conversation turn."""

    response: str
    tool_calls: list[str] = field(default_factory=list)
    iterations: int = 0
    used_tools: bool = False


class AgenticError(RuntimeError):
    """Raised when the agentic path cannot run (no tools, LLM failure)."""


class RaceEngineerAgent:
    """Tool-calling agent over the Oracle-backed F1 database."""

    def __init__(self, pool, ollama_client, model: str) -> None:
        self._pool = pool
        self._ollama = ollama_client
        self._model = model

    async def run(self, question: str) -> AgentResult:
        """Answer a question via the tool-calling loop.

        Args:
            question: The user's question.

        Returns:
            AgentResult with the final answer and trace.

        Raises:
            AgenticError: if the LLM cannot be used with tools.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        tool_calls_made: list[str] = []

        for iteration in range(1, MAX_AGENT_ITERATIONS + 1):
            try:
                response = await self._ollama.chat(
                    model=self._model,
                    messages=messages,
                    options={"temperature": 0.2},
                    think=False,
                    tools=TOOLS,
                )
            except Exception as exc:
                raise AgenticError(f"Ollama tool call failed: {exc}") from exc

            message = response.get("message", {})
            tool_calls = message.get("tool_calls")

            if not tool_calls:
                content = message.get("content", "").strip()
                if not content:
                    raise AgenticError("Empty assistant response in agent loop")
                return AgentResult(
                    response=content,
                    tool_calls=tool_calls_made,
                    iterations=iteration,
                    used_tools=bool(tool_calls_made),
                )

            # Execute each requested tool, then append the assistant's
            # tool_calls message verbatim (Ollama requires the exact shape)
            # followed by one tool result message per call.
            assistant_msg = dict(message)
            assistant_msg.pop("content", None)
            messages.append(assistant_msg)

            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                raw_args = function.get("arguments") or {}
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args

                if name not in _TOOL_NAMES:
                    result = {"error": f"Unknown tool: {name}"}
                else:
                    tool_calls_made.append(name)
                    try:
                        result = await self._execute_tool(name, args)
                    except Exception as exc:  # tool failure -> tell the LLM
                        logger.warning("Tool %s failed: %s", name, exc)
                        result = {"error": str(exc)[:300]}

                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, default=str)[:6000],
                })

        raise AgenticError(f"Agent loop exceeded {MAX_AGENT_ITERATIONS} iterations")

    # ------------------------------------------------------------------
    # Tool executors
    # ------------------------------------------------------------------
    async def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler: Callable[[dict[str, Any]], Any] = {
            "query_laps": self._tool_query_laps,
            "query_telemetry": self._tool_query_telemetry,
            "compare_laps": self._tool_compare_laps,
            "predict_tire_life": self._tool_tire_life,
            "predict_pit_window": self._tool_pit_window,
            "vector_search_laps": self._tool_vector_search,
            "search_documents": self._tool_search_documents,
            "query_setup": self._tool_query_setup,
        }[name]
        return await handler(args)

    async def _run_sql(self, sql: str, binds: dict | list | None = None) -> list[dict]:
        """Execute SQL and return rows as dicts."""
        async with self._pool.connection() as conn:
            cursor = conn.cursor()
            await cursor.execute(sql, binds or {})
            columns = [desc[0].lower() for desc in cursor.description or []]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]

    async def _tool_query_laps(self, args: dict[str, Any]) -> dict[str, Any]:
        sql = (
            "SELECT l.lap_id, l.lap_time_ms, l.sector1_ms, l.sector2_ms, l.sector3_ms, "
            "l.tire_compound, l.tire_age_laps, l.position, l.is_valid, "
            "d.code, d.first_name || ' ' || d.last_name AS driver, "
            "c.circuit_name AS circuit, s.session_type, s.season "
            "FROM laps l "
            "JOIN sessions s ON l.session_id = s.session_id "
            "JOIN circuits c ON s.circuit_id = c.circuit_id "
            "JOIN drivers d ON l.driver_id = d.driver_id "
            "WHERE (:driver IS NULL OR LOWER(d.code) LIKE '%' || LOWER(:driver) || '%' "
            "OR LOWER(d.first_name || ' ' || d.last_name) LIKE '%' || LOWER(:driver) || '%') "
            "AND (:circuit IS NULL OR LOWER(c.circuit_name) LIKE '%' || LOWER(:circuit) || '%') "
            "AND (:season IS NULL OR s.season = :season) "
            "AND (:session_type IS NULL OR LOWER(s.session_type) = LOWER(:session_type)) "
            "ORDER BY l.lap_time_ms NULLS LAST "
            "FETCH FIRST :limit ROWS ONLY"
        )
        binds = {
            "driver": args.get("driver"),
            "circuit": args.get("circuit"),
            "season": args.get("season"),
            "session_type": args.get("session_type"),
            "limit": int(args.get("limit", 10)),
        }
        rows = await self._run_sql(sql, binds)
        return {"rows": rows[:MAX_TOOL_RESULT_ROWS], "count": len(rows)}

    async def _tool_query_telemetry(self, args: dict[str, Any]) -> dict[str, Any]:
        lap_id = args.get("lap_id", "")
        limit = int(args.get("limit", 200))
        frames = await self._run_sql(
            "SELECT distance_m, speed_kph, throttle_pct, brake_pct, steering, gear, rpm, drs "
            "FROM telemetry_frames WHERE lap_id = :1 ORDER BY distance_m FETCH FIRST :2 ROWS ONLY",
            [lap_id, limit],
        )
        lap = await self._run_sql(
            f"SELECT {_LAP_COLUMNS} FROM laps WHERE lap_id = :1", [lap_id]
        )
        return {"lap_id": lap_id, "lap": lap[:1], "frames": frames}

    async def _tool_compare_laps(self, args: dict[str, Any]) -> dict[str, Any]:
        from api.routers.compare import (
            _align_telemetry,
            _compute_sector_deltas,
            _fetch_frames,
            _fetch_lap_row,
        )

        a = args.get("lap_id_a", "")
        b = args.get("lap_id_b", "")
        row_a = await _fetch_lap_row(self._pool, a)
        row_b = await _fetch_lap_row(self._pool, b)
        if row_a is None or row_b is None:
            return {"error": f"Lap not found: {a if row_a is None else b}"}

        frames_a = await _fetch_frames(self._pool, a)
        frames_b = await _fetch_frames(self._pool, b)
        deltas = _align_telemetry(frames_a, frames_b)
        sector_deltas = _compute_sector_deltas([row_a, row_b])

        # Summarize deltas for the LLM (avoid dumping hundreds of points)
        summary = {
            "lap_a_time_ms": row_a[7],
            "lap_b_time_ms": row_b[7],
            "sector_deltas": sector_deltas,
            "delta_points": len(deltas),
        }
        if deltas:
            max_speed_gain = max(deltas, key=lambda d: d.speed_delta)
            max_speed_loss = min(deltas, key=lambda d: d.speed_delta)
            summary["biggest_speed_gain_m"] = {
                "distance_m": max_speed_gain.distance_m,
                "speed_delta_kph": max_speed_gain.speed_delta,
            }
            summary["biggest_speed_loss_m"] = {
                "distance_m": max_speed_loss.distance_m,
                "speed_delta_kph": max_speed_loss.speed_delta,
            }
            # Sample every 10th delta point for detail
            summary["sample_deltas"] = [
                d.model_dump() for d in deltas[:: max(1, len(deltas) // 20)]
            ]
        return summary

    async def _tool_tire_life(self, args: dict[str, Any]) -> dict[str, Any]:
        return await strategy.tire_life(
            self._pool,
            compound=args.get("tire_compound", ""),
            tire_age_laps=int(args.get("tire_age_laps", 1)),
            track_temp_c=float(args.get("track_temp_c", 30.0)),
            fuel_load_kg=float(args.get("fuel_load_kg", 50.0)),
        )

    async def _tool_pit_window(self, args: dict[str, Any]) -> dict[str, Any]:
        return await strategy.pit_window(
            self._pool,
            current_lap=int(args.get("current_lap", 1)),
            total_laps=int(args.get("total_laps", 53)),
            tire_compound=args.get("tire_compound", ""),
            tire_age_laps=int(args.get("tire_age_laps", 1)),
            gap_ahead_ms=args.get("gap_ahead_ms"),
            gap_behind_ms=args.get("gap_behind_ms"),
        )

    async def _tool_vector_search(self, args: dict[str, Any]) -> dict[str, Any]:
        top_k = int(args.get("top_k", 5))
        sql = (
            "SELECT l.lap_id, l.lap_time_ms, d.code, c.circuit_name AS circuit, "
            "ROUND(VECTOR_DISTANCE(l.lap_embedding, "
            "(SELECT lap_embedding FROM laps WHERE driver_id = "
            "(SELECT driver_id FROM drivers WHERE is_sim_player = 1) "
            "ORDER BY lap_id DESC FETCH FIRST 1 ROW ONLY), COSINE), 4) AS similarity "
            "FROM laps l "
            "JOIN drivers d ON l.driver_id = d.driver_id "
            "JOIN sessions s ON l.session_id = s.session_id "
            "JOIN circuits c ON s.circuit_id = c.circuit_id "
            "WHERE l.lap_embedding IS NOT NULL "
            "ORDER BY similarity "
            "FETCH FIRST :k ROWS ONLY"
        )
        rows = await self._run_sql(sql, {"k": top_k})
        return {"rows": rows, "count": len(rows)}

    async def _tool_search_documents(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "")
        top_k = int(args.get("top_k", 3))
        sql = (
            f"WITH q AS (SELECT VECTOR_EMBEDDING({DOC_EMBEDDING_MODEL} USING :q AS DATA) AS qv FROM dual) "
            "SELECT d.doc_id, d.title, d.doc_type, "
            "DBMS_LOB.SUBSTR(d.content, 2000, 1) AS content, "
            "ROUND(VECTOR_DISTANCE(d.content_embedding, q.qv, COSINE), 4) AS similarity "
            "FROM race_documents d, q "
            "WHERE d.content_embedding IS NOT NULL "
            "ORDER BY similarity "
            "FETCH FIRST :k ROWS ONLY"
        )
        rows = await self._run_sql(sql, {"q": query, "k": top_k})
        return {"rows": rows[:MAX_TOOL_RESULT_ROWS], "count": len(rows)}

    async def _tool_query_setup(self, args: dict[str, Any]) -> dict[str, Any]:
        sql = (
            "SELECT cs.setup_id, cs.session_id, d.code AS driver, "
            "cs.front_wing, cs.rear_wing, cs.front_camber, cs.rear_camber, "
            "cs.front_toe, cs.rear_toe, cs.front_suspension, cs.rear_suspension, "
            "cs.front_arb, cs.rear_arb, cs.front_ride_height, cs.rear_ride_height, "
            "cs.brake_pressure, cs.brake_bias_pct, cs.diff_on_pct, cs.diff_off_pct, "
            "cs.ballast, cs.created_at "
            "FROM car_setups cs "
            "JOIN drivers d ON cs.driver_id = d.driver_id "
            "WHERE (:session IS NULL OR cs.session_id = :session) "
            "AND (:driver IS NULL OR LOWER(d.code) = LOWER(:driver)) "
            "ORDER BY cs.created_at DESC "
            "FETCH FIRST :limit ROWS ONLY"
        )
        binds = {
            "session": args.get("session_id"),
            "driver": args.get("driver_code"),
            "limit": int(args.get("limit", 3)),
        }
        rows = await self._run_sql(sql, binds)
        return {"rows": rows[:MAX_TOOL_RESULT_ROWS], "count": len(rows)}
