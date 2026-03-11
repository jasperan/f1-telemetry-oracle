"""RAG pipeline -- query understanding, context assembly, response generation.

Implements the AI Race Engineer's ability to:
1. Parse natural language questions into structured intents + entities
2. Generate multi-path retrieval queries (SQL, vector search, graph)
3. Assemble context from multiple data sources
4. Generate grounded, data-rich responses via Ollama

All LLM calls use Ollama native /api/chat with think: false.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Supported intents the query parser can extract
SUPPORTED_INTENTS = [
    "sector_analysis",    # Why am I slow in sector X?
    "comparison",         # Compare my lap to driver Y
    "tire_strategy",      # When should I pit? Tire life?
    "setup_advice",       # What setup changes for more rear grip?
    "historical",         # Who won the 2023 British GP?
    "lap_analysis",       # Analyze my last lap
    "general",            # Fallback for anything else
]

QUERY_UNDERSTANDING_PROMPT = """You are an F1 race engineer AI. Parse the user's question into a structured JSON object.

Extract:
- "intent": one of {intents}
- "entities": relevant entities (driver, circuit, sector, season, compound, lap_number, etc.)
- "filters": any SQL-style filters (season, session_type, source, etc.)

IMPORTANT: Return ONLY valid JSON, no markdown, no explanation.

Examples:
- "Why am I slow in sector 2 at Silverstone?" -> {{"intent": "sector_analysis", "entities": {{"sector": 2, "circuit": "silverstone"}}, "filters": {{}}}}
- "Compare my lap to Verstappen" -> {{"intent": "comparison", "entities": {{"driver": "verstappen", "comparison_type": "lap"}}, "filters": {{}}}}
- "When should I pit?" -> {{"intent": "tire_strategy", "entities": {{}}, "filters": {{}}}}
- "Who won the 2023 British GP?" -> {{"intent": "historical", "entities": {{"season": 2023, "circuit": "silverstone"}}, "filters": {{"season": 2023}}}}

User question: {question}"""


@dataclass
class ParsedQuery:
    """Result of parsing a natural language question."""

    intent: str
    entities: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    raw_question: str = ""

    def to_sql_queries(self) -> list[str]:
        """Generate SQL query skeletons based on parsed intent and entities.

        Returns:
            List of parameterized SQL strings for data retrieval.
        """
        queries: list[str] = []

        if self.intent == "sector_analysis":
            sector = self.entities.get("sector")
            circuit = self.entities.get("circuit", "")
            queries.append(
                f"SELECT l.lap_id, l.sector{sector}_time_ms, l.lap_time_ms, "
                f"d.driver_code, c.name AS circuit_name "
                f"FROM laps l "
                f"JOIN sessions s ON l.session_id = s.session_id "
                f"JOIN circuits c ON s.circuit_id = c.circuit_id "
                f"JOIN drivers d ON l.driver_id = d.driver_id "
                f"WHERE LOWER(c.name) LIKE '%{circuit}%' "
                f"ORDER BY l.sector{sector}_time_ms ASC "
                f"FETCH FIRST 20 ROWS ONLY"
            )
            queries.append(
                f"SELECT tf.distance_m, tf.speed_kph, tf.throttle, tf.brake, tf.steering "
                f"FROM telemetry_frames tf "
                f"JOIN laps l ON tf.lap_id = l.lap_id "
                f"JOIN sessions s ON l.session_id = s.session_id "
                f"JOIN circuits c ON s.circuit_id = c.circuit_id "
                f"WHERE LOWER(c.name) LIKE '%{circuit}%' "
                f"AND l.driver_id = (SELECT driver_id FROM drivers WHERE is_sim_player = 1) "
                f"ORDER BY tf.distance_m"
            )

        elif self.intent == "comparison":
            driver = self.entities.get("driver", "")
            queries.append(
                f"SELECT l.lap_id, l.lap_time_ms, l.sector1_time_ms, "
                f"l.sector2_time_ms, l.sector3_time_ms, d.driver_code "
                f"FROM laps l "
                f"JOIN drivers d ON l.driver_id = d.driver_id "
                f"WHERE LOWER(d.driver_code) LIKE '%{driver}%' "
                f"OR LOWER(d.name) LIKE '%{driver}%' "
                f"ORDER BY l.lap_time_ms ASC "
                f"FETCH FIRST 10 ROWS ONLY"
            )

        elif self.intent == "tire_strategy":
            queries.append(
                "SELECT l.lap_number, l.tire_compound, l.tire_age_laps, "
                "l.lap_time_ms, l.sector1_time_ms, l.sector2_time_ms, l.sector3_time_ms "
                "FROM laps l "
                "JOIN sessions s ON l.session_id = s.session_id "
                "WHERE l.driver_id = (SELECT driver_id FROM drivers WHERE is_sim_player = 1) "
                "AND s.session_id = (SELECT MAX(session_id) FROM sessions WHERE source = 'sim') "
                "ORDER BY l.lap_number"
            )

        elif self.intent == "historical":
            season = self.filters.get("season", "")
            circuit = self.entities.get("circuit", "")
            queries.append(
                f"SELECT d.name AS driver_name, d.driver_code, t.name AS team_name, "
                f"l.lap_time_ms, l.position, s.started_at "
                f"FROM laps l "
                f"JOIN sessions s ON l.session_id = s.session_id "
                f"JOIN circuits c ON s.circuit_id = c.circuit_id "
                f"JOIN drivers d ON l.driver_id = d.driver_id "
                f"JOIN teams t ON d.team_id = t.team_id "
                f"WHERE LOWER(c.name) LIKE '%{circuit}%' "
                + (f"AND EXTRACT(YEAR FROM s.started_at) = {season} " if season else "")
                + "ORDER BY l.position ASC "
                "FETCH FIRST 20 ROWS ONLY"
            )

        elif self.intent == "lap_analysis":
            queries.append(
                "SELECT l.lap_id, l.lap_time_ms, l.sector1_time_ms, "
                "l.sector2_time_ms, l.sector3_time_ms, l.tire_compound, "
                "l.tire_age_laps, l.fuel_load_kg "
                "FROM laps l "
                "WHERE l.driver_id = (SELECT driver_id FROM drivers WHERE is_sim_player = 1) "
                "ORDER BY l.lap_id DESC "
                "FETCH FIRST 5 ROWS ONLY"
            )

        else:
            # General: fetch recent laps for context
            queries.append(
                "SELECT l.lap_id, l.lap_time_ms, d.driver_code, c.name AS circuit "
                "FROM laps l "
                "JOIN sessions s ON l.session_id = s.session_id "
                "JOIN circuits c ON s.circuit_id = c.circuit_id "
                "JOIN drivers d ON l.driver_id = d.driver_id "
                "ORDER BY l.lap_id DESC "
                "FETCH FIRST 10 ROWS ONLY"
            )

        return queries

    def to_vector_search_params(self) -> dict[str, Any]:
        """Generate parameters for Oracle AI Vector Search.

        Returns:
            Dict with top_k, distance_metric, and optional filters.
        """
        params: dict[str, Any] = {
            "top_k": 5,
            "distance_metric": "COSINE",
        }

        if self.intent == "comparison":
            params["top_k"] = 10  # more candidates for comparison
        elif self.intent == "sector_analysis":
            params["top_k"] = 5

        # Pass through entity-based filters
        if "circuit" in self.entities:
            params["circuit_filter"] = self.entities["circuit"]
        if "driver" in self.entities:
            params["driver_filter"] = self.entities["driver"]
        if "season" in self.filters:
            params["season_filter"] = self.filters["season"]

        return params

    def to_graph_traversal(self) -> str | None:
        """Generate an Oracle Graph PGQL query if relationships are needed.

        Returns:
            PGQL query string or None if graph traversal is not needed.
        """
        if self.intent == "historical" and "driver" in self.entities:
            driver = self.entities["driver"]
            return (
                f"SELECT d.name, t.name AS team, c.name AS circuit, r.position "
                f"FROM MATCH (d:Driver)-[:DROVE_FOR]->(t:Team), "
                f"MATCH (d)-[:RACED_AT]->(c:Circuit) "
                f"WHERE LOWER(d.code) = '{driver}' "
                f"ORDER BY r.season DESC"
            )
        return None


class QueryUnderstanding:
    """Parses natural language questions into structured intents + entities.

    Uses Ollama (Qwen3.5-35B-A3B, think=false) to extract structured
    information from user questions.
    """

    def __init__(self, ollama_client) -> None:
        self._ollama = ollama_client

    async def parse(self, question: str) -> ParsedQuery:
        """Parse a natural language question into a ParsedQuery.

        Args:
            question: The user's natural language question.

        Returns:
            ParsedQuery with intent, entities, and filters.
        """
        prompt = QUERY_UNDERSTANDING_PROMPT.format(
            intents=", ".join(SUPPORTED_INTENTS),
            question=question,
        )

        try:
            response = await self._ollama.chat(
                model="qwen3.5:35b-a3b",
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0},
                think=False,
            )

            content = response["message"]["content"].strip()

            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            parsed = json.loads(content)

            intent = parsed.get("intent", "general")
            if intent not in SUPPORTED_INTENTS:
                intent = "general"

            return ParsedQuery(
                intent=intent,
                entities=parsed.get("entities", {}),
                filters=parsed.get("filters", {}),
                raw_question=question,
            )

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse LLM response for query: %s -- %s", question, exc)
            return ParsedQuery(
                intent="general",
                entities={},
                filters={},
                raw_question=question,
            )


class ContextAssembler:
    """Assembles context from multiple retrieval paths for response generation.

    Combines:
    - SQL query results (precise lookups)
    - Vector search results (similar patterns)
    - Graph traversal results (related entities)
    into a single context string for the response generator.
    """

    def __init__(self, oracle_pool) -> None:
        self._pool = oracle_pool

    async def assemble(
        self,
        parsed_query: ParsedQuery,
        sql_results: list[dict[str, Any]] | None = None,
        vector_results: list[dict[str, Any]] | None = None,
        graph_results: list[dict[str, Any]] | None = None,
    ) -> str:
        """Assemble context from multiple data sources.

        Args:
            parsed_query: The parsed user query.
            sql_results: Results from SQL queries.
            vector_results: Results from vector similarity search.
            graph_results: Results from graph traversal.

        Returns:
            Formatted context string for LLM response generation.
        """
        sections: list[str] = []

        sections.append(f"USER QUESTION: {parsed_query.raw_question}")
        sections.append(f"DETECTED INTENT: {parsed_query.intent}")
        sections.append(f"ENTITIES: {json.dumps(parsed_query.entities)}")

        if sql_results:
            sections.append("\n--- DATA FROM DATABASE ---")
            for i, row in enumerate(sql_results[:20], 1):
                sections.append(f"  [{i}] {json.dumps(row)}")

        if vector_results:
            sections.append("\n--- SIMILAR LAPS (Vector Search) ---")
            for i, row in enumerate(vector_results[:10], 1):
                similarity = row.get("similarity", "N/A")
                sections.append(f"  [{i}] similarity={similarity} -- {json.dumps(row)}")

        if graph_results:
            sections.append("\n--- RELATED ENTITIES (Graph) ---")
            for i, row in enumerate(graph_results[:10], 1):
                sections.append(f"  [{i}] {json.dumps(row)}")

        if not sql_results and not vector_results and not graph_results:
            sections.append("\n--- NO DATA FOUND ---")
            sections.append("  No matching data was found in the database.")

        return "\n".join(sections)

    async def execute_retrieval(self, parsed_query: ParsedQuery) -> dict[str, list[dict]]:
        """Execute all retrieval paths and return combined results.

        Args:
            parsed_query: The parsed user query with SQL/vector/graph params.

        Returns:
            Dict with 'sql', 'vector', 'graph' keys containing result lists.
        """
        results: dict[str, list[dict]] = {
            "sql": [],
            "vector": [],
            "graph": [],
        }

        # Execute SQL queries
        sql_queries = parsed_query.to_sql_queries()
        for query in sql_queries:
            try:
                async with self._pool.connection() as conn:
                    cursor = conn.cursor()
                    await cursor.execute(query)
                    columns = [desc[0].lower() for desc in cursor.description or []]
                    rows = await cursor.fetchall()
                    for row in rows:
                        results["sql"].append(dict(zip(columns, row)))
            except Exception as exc:
                logger.warning("SQL retrieval failed: %s -- %s", query[:80], exc)

        # Execute vector search
        vs_params = parsed_query.to_vector_search_params()
        try:
            async with self._pool.connection() as conn:
                cursor = conn.cursor()
                top_k = vs_params["top_k"]
                # Vector search using Oracle AI Vector Search
                vector_sql = (
                    "SELECT l.lap_id, l.lap_time_ms, d.driver_code, "
                    "VECTOR_DISTANCE(l.lap_embedding, "
                    "(SELECT lap_embedding FROM laps WHERE driver_id = "
                    "(SELECT driver_id FROM drivers WHERE is_sim_player = 1) "
                    "ORDER BY lap_id DESC FETCH FIRST 1 ROW ONLY), COSINE) AS similarity "
                    "FROM laps l "
                    "JOIN drivers d ON l.driver_id = d.driver_id "
                    "WHERE l.lap_embedding IS NOT NULL "
                    "ORDER BY similarity "
                    f"FETCH FIRST {top_k} ROWS ONLY"
                )
                await cursor.execute(vector_sql)
                columns = [desc[0].lower() for desc in cursor.description or []]
                rows = await cursor.fetchall()
                for row in rows:
                    results["vector"].append(dict(zip(columns, row)))
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)

        # Execute graph traversal
        graph_query = parsed_query.to_graph_traversal()
        if graph_query:
            try:
                async with self._pool.connection() as conn:
                    cursor = conn.cursor()
                    await cursor.execute(graph_query)
                    columns = [desc[0].lower() for desc in cursor.description or []]
                    rows = await cursor.fetchall()
                    for row in rows:
                        results["graph"].append(dict(zip(columns, row)))
            except Exception as exc:
                logger.warning("Graph traversal failed: %s", exc)

        return results


class ResponseGenerator:
    """Generates grounded responses using assembled context and Ollama.

    Produces race-engineer-style answers with specific numbers,
    comparisons, and actionable suggestions.
    """

    SYSTEM_PROMPT = (
        "You are an expert F1 race engineer AI assistant. "
        "You analyze telemetry data, tire strategy, lap times, and historical results "
        "to give precise, data-driven advice. "
        "Always reference specific numbers from the provided data. "
        "Be concise but thorough. Use F1 terminology. "
        "If the data doesn't support a conclusion, say so honestly. "
        "Format important numbers in bold and use bullet points for comparisons."
    )

    def __init__(self, ollama_client) -> None:
        self._ollama = ollama_client

    async def generate(
        self,
        context: str,
        stream: bool = False,
    ):
        """Generate a grounded response from assembled context.

        Args:
            context: Formatted context string from ContextAssembler.
            stream: If True, yield response chunks for streaming.

        Returns:
            Complete response string, or async generator of chunks if stream=True.
        """
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]

        if stream:
            return self._stream_response(messages)
        else:
            response = await self._ollama.chat(
                model="qwen3.5:35b-a3b",
                messages=messages,
                options={"temperature": 0.3},
                think=False,
            )
            return response["message"]["content"]

    async def _stream_response(self, messages: list[dict]):
        """Stream response chunks from Ollama.

        Yields:
            String chunks as they arrive from the LLM.
        """
        async for chunk in await self._ollama.chat(
            model="qwen3.5:35b-a3b",
            messages=messages,
            options={"temperature": 0.3},
            think=False,
            stream=True,
        ):
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
