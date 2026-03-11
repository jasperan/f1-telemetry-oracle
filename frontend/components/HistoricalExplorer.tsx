"use client";

import { FormEvent, useCallback, useState } from "react";
import clsx from "clsx";

/** Result card from a historical search query. */
interface HistoricalResult {
  type: "race_result" | "driver_stat" | "circuit_info" | "season_summary";
  title: string;
  subtitle?: string;
  data: Record<string, string | number>;
  highlight?: string;
}

interface SearchResponse {
  query: string;
  intent: string;
  results: HistoricalResult[];
  answer: string;
  elapsed_ms: number;
}

/** Compact data row for result cards. */
function DataRow({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string | number;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="data-label">{label}</span>
      <span
        className={clsx(
          "font-mono text-data-sm tabular-nums",
          highlight ? "text-telemetry-speed" : "text-race-text"
        )}
      >
        {value}
      </span>
    </div>
  );
}

/** Result card component. */
function ResultCard({ result }: { result: HistoricalResult }) {
  const typeColors: Record<string, string> = {
    race_result: "border-team-ferrari/30",
    driver_stat: "border-telemetry-speed/30",
    circuit_info: "border-telemetry-throttle/30",
    season_summary: "border-telemetry-steering/30",
  };

  const typeLabels: Record<string, string> = {
    race_result: "RACE",
    driver_stat: "DRIVER",
    circuit_info: "CIRCUIT",
    season_summary: "SEASON",
  };

  return (
    <div
      className={clsx(
        "rounded-lg border bg-race-surface p-3 transition-colors hover:bg-race-card",
        typeColors[result.type] ?? "border-race-border"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="text-data-xs font-mono text-race-muted uppercase mr-2">
            {typeLabels[result.type] ?? result.type}
          </span>
          <span className="font-mono text-data-sm text-race-text font-medium">
            {result.title}
          </span>
        </div>
      </div>

      {result.subtitle && (
        <p className="text-data-xs text-race-muted mb-2">{result.subtitle}</p>
      )}

      {/* Data rows */}
      <div className="space-y-0.5">
        {Object.entries(result.data).map(([key, value]) => (
          <DataRow
            key={key}
            label={key.replace(/_/g, " ")}
            value={value}
            highlight={result.highlight === key}
          />
        ))}
      </div>
    </div>
  );
}

/** Suggested historical queries. */
const SUGGESTIONS = [
  "Who won the 2023 British GP?",
  "Verstappen's win record in 2023",
  "Fastest lap at Monza all time",
  "McLaren results in 2024",
  "Rain races at Spa",
  "Hamilton vs Verstappen head to head",
];

export default function HistoricalExplorer() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/chat/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: searchQuery,
          include_telemetry: false,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const json = await res.json();

      // Parse the response into structured results
      const searchResponse: SearchResponse = {
        query: searchQuery,
        intent: json.intent ?? "historical",
        results: parseResultsFromResponse(json.response, json.entities),
        answer: json.response,
        elapsed_ms: json.elapsed_ms ?? 0,
      };

      setResponse(searchResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    search(query);
  };

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Historical Explorer</span>
        {response && (
          <span className="text-data-xs font-mono text-race-muted">
            {response.elapsed_ms}ms
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Search bar */}
        <form
          onSubmit={onFormSubmit}
          className="px-3 pt-3 pb-2 flex gap-2"
        >
          <div className="flex-1 relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search F1 history..."
              className={clsx(
                "w-full bg-race-surface border border-race-border rounded-lg pl-3 pr-8 py-2",
                "text-data-sm font-sans text-race-text placeholder:text-race-muted",
                "focus:outline-none focus:border-telemetry-speed/50"
              )}
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setResponse(null);
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-race-muted hover:text-race-text"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={!query.trim() || loading}
            className={clsx(
              "px-3 py-2 rounded-lg font-mono text-data-xs transition-colors",
              query.trim() && !loading
                ? "bg-telemetry-speed/20 text-telemetry-speed border border-telemetry-speed/30 hover:bg-telemetry-speed/30"
                : "bg-race-surface text-race-muted border border-race-border cursor-not-allowed"
            )}
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-telemetry-speed border-t-transparent rounded-full animate-spin" />
            ) : (
              "SEARCH"
            )}
          </button>
        </form>

        {/* Results area */}
        <div className="flex-1 overflow-y-auto px-3 pb-3">
          {/* Error state */}
          {error && (
            <div className="text-center py-4">
              <span className="text-data-sm text-telemetry-brake font-mono">
                {error}
              </span>
            </div>
          )}

          {/* Empty state -- suggestions */}
          {!response && !loading && !error && (
            <div className="py-4">
              <p className="text-data-xs text-race-muted mb-3">
                SUGGESTED QUERIES
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => {
                      setQuery(suggestion);
                      search(suggestion);
                    }}
                    className="px-2.5 py-1.5 rounded-lg border border-race-border text-data-xs
                      font-mono text-race-muted hover:border-telemetry-speed/30
                      hover:text-telemetry-speed transition-colors text-left"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="flex items-center justify-center py-8">
              <div className="flex flex-col items-center gap-2">
                <div className="w-6 h-6 border-2 border-telemetry-speed border-t-transparent rounded-full animate-spin" />
                <span className="text-data-xs text-race-muted font-mono">
                  Searching historical data...
                </span>
              </div>
            </div>
          )}

          {/* Results */}
          {response && !loading && (
            <div className="flex flex-col gap-3">
              {/* AI answer */}
              <div className="bg-race-card border border-race-border rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-5 h-5 rounded-full bg-telemetry-throttle/20 flex items-center justify-center">
                    <span className="text-data-xs font-mono text-telemetry-throttle font-bold">
                      AI
                    </span>
                  </div>
                  <span className="text-data-xs text-race-muted font-mono uppercase">
                    {response.intent}
                  </span>
                </div>
                <p className="text-data-sm text-race-text leading-relaxed">
                  {response.answer}
                </p>
              </div>

              {/* Result cards */}
              {response.results.length > 0 && (
                <div className="flex flex-col gap-2">
                  <span className="data-label">
                    {response.results.length} RESULT
                    {response.results.length !== 1 ? "S" : ""}
                  </span>
                  {response.results.map((result, i) => (
                    <ResultCard key={i} result={result} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Parse structured result cards from the AI response text.
 * This is a best-effort extraction -- the AI response is free-form text,
 * so we look for patterns like driver names, lap times, positions.
 */
function parseResultsFromResponse(
  responseText: string,
  entities: Record<string, unknown>
): HistoricalResult[] {
  const results: HistoricalResult[] = [];

  // Look for tabular data patterns in the response
  const lines = responseText.split("\n").filter((l) => l.trim());

  // Try to extract position-based results (e.g., "1. Verstappen - 1:23.456")
  const positionPattern = /(\d+)\.\s+(\w[\w\s]*?)[\s\-]+(\d+:\d+\.\d+)/;
  const positionMatches = lines
    .map((l) => l.match(positionPattern))
    .filter(Boolean);

  if (positionMatches.length > 0) {
    for (const match of positionMatches) {
      if (!match) continue;
      results.push({
        type: "race_result",
        title: match[2].trim(),
        data: {
          position: parseInt(match[1]),
          time: match[3],
        },
        highlight: "position",
      });
    }
  }

  // If no structured data found, create a single summary card
  if (results.length === 0 && responseText.length > 0) {
    const summaryData: Record<string, string | number> = {};

    if (entities?.season)
      summaryData.season = entities.season as number;
    if (entities?.circuit)
      summaryData.circuit = entities.circuit as string;
    if (entities?.driver)
      summaryData.driver = entities.driver as string;

    if (Object.keys(summaryData).length > 0) {
      results.push({
        type: "season_summary",
        title: "Query Result",
        subtitle: responseText.slice(0, 120) + (responseText.length > 120 ? "..." : ""),
        data: summaryData,
      });
    }
  }

  return results;
}
