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
          "font-mono text-data-sm",
          highlight ? "text-accent-primary font-medium" : "text-race-text"
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
    race_result: "border-team-ferrari/20",
    driver_stat: "border-accent-primary/20",
    circuit_info: "border-accent-positive/20",
    season_summary: "border-accent-warning/20",
  };

  const typeLabels: Record<string, string> = {
    race_result: "Race",
    driver_stat: "Driver",
    circuit_info: "Circuit",
    season_summary: "Season",
  };

  return (
    <div
      className={clsx(
        "rounded-xl border bg-race-surface/60 p-3 transition-all duration-200 hover:bg-race-card/80 hover:border-opacity-40",
        typeColors[result.type] ?? "border-race-border/30"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[0.6rem] font-mono text-race-muted/60 uppercase tracking-wider">
            {typeLabels[result.type] ?? result.type}
          </span>
          <span className="font-mono text-data-sm text-race-text font-medium">
            {result.title}
          </span>
        </div>
      </div>

      {result.subtitle && (
        <p className="text-data-xs text-race-muted/60 mb-2 leading-relaxed">{result.subtitle}</p>
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
    <article className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Historical explorer</span>
        {response && (
          <span className="text-data-xs font-mono text-race-muted/50">
            {response.elapsed_ms}ms
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Search bar */}
        <form
          onSubmit={onFormSubmit}
          className="px-3.5 pt-3 pb-2 flex gap-2"
        >
          <div className="flex-1 relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search F1 history..."
              className="input-field pr-8"
              aria-label="Historical search query"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setResponse(null);
                }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-race-muted/50 hover:text-race-text transition-colors duration-200"
                aria-label="Clear search"
              >
                <svg
                  className="w-3.5 h-3.5"
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
            className="btn-primary text-data-xs"
          >
            {loading ? (
              <div className="w-3.5 h-3.5 spinner" />
            ) : (
              "Search"
            )}
          </button>
        </form>

        {/* Results area */}
        <div className="flex-1 overflow-y-auto px-3.5 pb-3">
          {/* Error state */}
          {error && (
            <div className="text-center py-4 animate-fade-in">
              <span className="text-data-sm text-accent-negative font-mono">
                {error}
              </span>
            </div>
          )}

          {/* Empty state -- suggestions */}
          {!response && !loading && !error && (
            <div className="py-4 animate-fade-in">
              <p className="data-label mb-3">
                Suggested queries
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => {
                      setQuery(suggestion);
                      search(suggestion);
                    }}
                    className="pill-btn text-left"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="flex items-center justify-center py-8 animate-fade-in">
              <div className="flex flex-col items-center gap-2.5">
                <div className="w-5 h-5 spinner" />
                <span className="text-data-xs text-race-muted/50 font-mono">
                  Searching historical data...
                </span>
              </div>
            </div>
          )}

          {/* Results */}
          {response && !loading && (
            <div className="flex flex-col gap-3 animate-fade-in-up">
              {/* AI answer */}
              <div className="bg-race-card/70 border border-race-border/40 rounded-xl p-3.5">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-5 h-5 rounded-md bg-accent-positive/12 flex items-center justify-center border border-accent-positive/15">
                    <span className="text-[0.55rem] font-mono text-accent-positive font-bold">
                      AI
                    </span>
                  </div>
                  <span className="text-data-xs text-race-muted/50 font-mono uppercase tracking-wider">
                    {response.intent}
                  </span>
                </div>
                <p className="text-data-sm text-race-text/85 leading-relaxed">
                  {response.answer}
                </p>
              </div>

              {/* Result cards */}
              {response.results.length > 0 && (
                <div className="flex flex-col gap-2">
                  <span className="data-label">
                    {response.results.length} result
                    {response.results.length !== 1 ? "s" : ""}
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
    </article>
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
