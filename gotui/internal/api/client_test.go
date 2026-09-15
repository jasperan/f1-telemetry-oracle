package api

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// --- base URL validation ----------------------------------------------------

// TestValidateBaseURL catches a typo while the user is still typing it.
func TestValidateBaseURL(t *testing.T) {
	cases := []struct {
		name    string
		in      string
		wantErr bool
	}{
		{"default", "http://127.0.0.1:8100", false},
		{"https", "https://f1.example.com", false},
		{"blank", "   ", true},
		{"no scheme", "127.0.0.1:8100", true},
		{"wrong scheme", "ftp://127.0.0.1", true},
		{"no host", "http://", true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := ValidateBaseURL(c.in)
			if (err != nil) != c.wantErr {
				t.Fatalf("ValidateBaseURL(%q) error = %v, wantErr %v", c.in, err, c.wantErr)
			}
		})
	}
}

// --- transport --------------------------------------------------------------

// TestHealthDecodesTheServiceShape keeps the one endpoint that tells "service
// down" apart from "database down" honest.
func TestHealthDecodesTheServiceShape(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			t.Errorf("path = %q, want /health", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer server.Close()

	got, err := NewClient(server.URL).Health(context.Background())
	if err != nil {
		t.Fatalf("Health: %v", err)
	}
	if got.Status != "ok" {
		t.Errorf("status = %q, want ok", got.Status)
	}
}

// TestUnreachableIsDistinguishable is the whole point of ErrUnreachable: the UI
// must say "start the API", not print a connection-refused trace.
func TestUnreachableIsDistinguishable(t *testing.T) {
	// Port 1 on loopback refuses immediately; nothing is ever listening there.
	_, err := NewClient("http://127.0.0.1:1").Health(context.Background())
	if err == nil {
		t.Fatal("Health against a dead port returned no error")
	}
	if !errors.Is(err, ErrUnreachable) {
		t.Fatalf("error = %v, want it to wrap ErrUnreachable", err)
	}
}

// TestServerErrorIsClassifiedAsOracleDown keeps "database is not up" separate
// from a bad request, since the two need different advice.
func TestServerErrorIsClassifiedAsOracleDown(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"detail":"ORA-12541: TNS:no listener"}`))
	}))
	defer server.Close()

	_, err := NewClient(server.URL).Circuits(context.Background(), 5)
	if err == nil {
		t.Fatal("Circuits against a 500 returned no error")
	}
	if !errors.Is(err, ErrOracleDown) {
		t.Fatalf("error = %v, want it to wrap ErrOracleDown", err)
	}
	if !strings.Contains(err.Error(), "ORA-12541") {
		t.Errorf("error = %v, want the service's own detail text", err)
	}
}

// TestClientErrorKeepsTheDetailButIsNotOracleDown covers FastAPI's 400/404 path.
func TestClientErrorKeepsTheDetailButIsNotOracleDown(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Lap 'nope' not found"}`))
	}))
	defer server.Close()

	_, err := NewClient(server.URL).SimVsReal(context.Background(), "nope")
	if err == nil {
		t.Fatal("SimVsReal against a 404 returned no error")
	}
	if errors.Is(err, ErrOracleDown) {
		t.Errorf("a 404 was classified as ErrOracleDown: %v", err)
	}
	if !strings.Contains(err.Error(), "not found") {
		t.Errorf("error = %v, want the service's detail", err)
	}
}

// TestDetailFallsBackToTheBody keeps an HTML error page diagnosable.
func TestDetailFallsBackToTheBody(t *testing.T) {
	if got := detail([]byte(`{"detail":"boom"}`)); got != "boom" {
		t.Errorf("detail = %q, want boom", got)
	}
	if got := detail([]byte(`{"detail":{"nested":1}}`)); !strings.Contains(got, "nested") {
		t.Errorf("detail = %q, want the encoded nested object", got)
	}
	if got := detail(nil); got != "(empty response)" {
		t.Errorf("detail(nil) = %q, want the empty marker", got)
	}
	long := strings.Repeat("x", 500)
	if got := detail([]byte(long)); len(got) > 320 {
		t.Errorf("detail truncated to %d chars, want a short preview", len(got))
	}
}

// --- endpoints and query construction ---------------------------------------

// TestCircuitsDecodesAndLimits checks the decode and that the limit is sent.
func TestCircuitsDecodesAndLimits(t *testing.T) {
	var gotQuery string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		_, _ = w.Write([]byte(`[{"circuit_id":"bahrain","circuit_name":"Bahrain International Circuit","country":"Bahrain","track_length_m":5412.0}]`))
	}))
	defer server.Close()

	got, err := NewClient(server.URL).Circuits(context.Background(), 25)
	if err != nil {
		t.Fatalf("Circuits: %v", err)
	}
	if gotQuery != "limit=25" {
		t.Errorf("query = %q, want limit=25", gotQuery)
	}
	if len(got) != 1 || got[0].CircuitID != "bahrain" {
		t.Fatalf("decoded %+v, want one Bahrain circuit", got)
	}
	if got[0].DisplayName() != "Bahrain International Circuit" {
		t.Errorf("DisplayName = %q", got[0].DisplayName())
	}
	if got[0].TrackLengthM == nil || *got[0].TrackLengthM != 5412 {
		t.Errorf("track length = %v, want 5412", got[0].TrackLengthM)
	}
}

// TestSessionsSendsTheSourceFilterOnlyWhenAsked keeps an empty filter as "all",
// which is what the select's "any" option means.
func TestSessionsSendsTheSourceFilterOnlyWhenAsked(t *testing.T) {
	var gotQuery string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		_, _ = w.Write([]byte(`[{"session_id":"s1","circuit_id":"bahrain","session_type":"race","source":"sim"}]`))
	}))
	defer server.Close()
	client := NewClient(server.URL)

	if _, err := client.Sessions(context.Background(), "", 10); err != nil {
		t.Fatalf("Sessions: %v", err)
	}
	if strings.Contains(gotQuery, "source=") {
		t.Errorf("query = %q, want no source filter for an empty value", gotQuery)
	}

	if _, err := client.Sessions(context.Background(), "openf1", 10); err != nil {
		t.Fatalf("Sessions: %v", err)
	}
	if !strings.Contains(gotQuery, "source=openf1") {
		t.Errorf("query = %q, want source=openf1", gotQuery)
	}
}

// TestLapsDecodesNullableSectors keeps a partially recorded lap renderable.
func TestLapsDecodesNullableSectors(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`[{"lap_id":"l1","session_id":"s1","driver_id":"d1","lap_number":3,` +
			`"sector1_ms":30000,"sector2_ms":null,"sector3_ms":25000,"lap_time_ms":83000,` +
			`"tire_compound":"SOFT","is_valid":true}]`))
	}))
	defer server.Close()

	got, err := NewClient(server.URL).Laps(context.Background(), "s1", "d1", 10)
	if err != nil {
		t.Fatalf("Laps: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("got %d laps, want 1", len(got))
	}
	if got[0].Sector2Ms != nil {
		t.Errorf("sector2 = %v, want nil for a missing sector", got[0].Sector2Ms)
	}
	if got[0].LapTimeMs == nil || *got[0].LapTimeMs != 83000 {
		t.Errorf("lap time = %v, want 83000", got[0].LapTimeMs)
	}
}

// TestCompareLapsRequiresTwoIDs mirrors the service's own 400 so the form can
// reject it before a round trip.
func TestCompareLapsRequiresTwoIDs(t *testing.T) {
	client := NewClient("http://127.0.0.1:1")
	if _, err := client.CompareLaps(context.Background(), []string{"only-one"}); err == nil {
		t.Fatal("CompareLaps accepted a single lap ID")
	}
	// Blank entries must be stripped, not counted towards the pair.
	if _, err := client.CompareLaps(context.Background(), []string{"a", "  "}); err == nil {
		t.Fatal("CompareLaps counted a blank ID towards the two required")
	}
}

// TestCompareLapsBuildsTheCommaList watches the exact query the service parses.
func TestCompareLapsBuildsTheCommaList(t *testing.T) {
	var gotIDs string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotIDs = r.URL.Query().Get("ids")
		_, _ = w.Write([]byte(`{"lap_ids":["a","b"],"deltas":[{"distance_m":100,"speed_delta":-4.5}],` +
			`"sector_deltas":{"sector1_ms":[30000,29500]}}`))
	}))
	defer server.Close()

	got, err := NewClient(server.URL).CompareLaps(context.Background(), []string{"a", "b"})
	if err != nil {
		t.Fatalf("CompareLaps: %v", err)
	}
	if gotIDs != "a,b" {
		t.Errorf("ids = %q, want a,b", gotIDs)
	}
	if len(got.Deltas) != 1 || got.Deltas[0].SpeedDelta != -4.5 {
		t.Errorf("deltas = %+v, want one point with speed -4.5", got.Deltas)
	}
	if len(got.SectorDeltas["sector1_ms"]) != 2 {
		t.Errorf("sector times = %v, want two entries", got.SectorDeltas["sector1_ms"])
	}
}

// TestSimVsRealRejectsABlankLapID avoids a pointless request.
func TestSimVsRealRejectsABlankLapID(t *testing.T) {
	if _, err := NewClient("http://127.0.0.1:1").SimVsReal(context.Background(), "   "); err == nil {
		t.Fatal("SimVsReal accepted a blank lap id")
	}
}

// --- strategy simulation validation -----------------------------------------

// TestValidateStrategySimMirrorsTheServiceBounds means an out-of-range value is
// reported in the form rather than coming back as an opaque 422.
func TestValidateStrategySimMirrorsTheServiceBounds(t *testing.T) {
	valid := StrategySimRequest{TotalLaps: 53, TrackTempC: 30, FuelStartKg: 110, NSims: 500, Seed: 42}
	if err := ValidateStrategySim(valid); err != nil {
		t.Fatalf("a valid request was rejected: %v", err)
	}

	cases := []struct {
		name string
		mut  func(*StrategySimRequest)
	}{
		{"too few laps", func(r *StrategySimRequest) { r.TotalLaps = 1 }},
		{"too many laps", func(r *StrategySimRequest) { r.TotalLaps = 121 }},
		{"cold track", func(r *StrategySimRequest) { r.TrackTempC = -1 }},
		{"hot track", func(r *StrategySimRequest) { r.TrackTempC = 61 }},
		{"negative fuel", func(r *StrategySimRequest) { r.FuelStartKg = -1 }},
		{"too much fuel", func(r *StrategySimRequest) { r.FuelStartKg = 151 }},
		{"too few sims", func(r *StrategySimRequest) { r.NSims = 49 }},
		{"too many sims", func(r *StrategySimRequest) { r.NSims = 5001 }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			req := valid
			c.mut(&req)
			if err := ValidateStrategySim(req); err == nil {
				t.Fatalf("ValidateStrategySim accepted %+v", req)
			}
		})
	}
}

// TestStrategySimDecodesTheRankedStrategies pins the shape the strategy screen
// renders, including the percentile band.
func TestStrategySimDecodesTheRankedStrategies(t *testing.T) {
	var body string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method = %s, want POST", r.Method)
		}
		if r.URL.Path != "/api/predict/strategy-sim" {
			t.Errorf("path = %q", r.URL.Path)
		}
		buf := make([]byte, r.ContentLength)
		_, _ = r.Body.Read(buf)
		body = string(buf)
		_, _ = w.Write([]byte(`{"total_laps":53,"track_temp_c":30,"n_sims":500,"fastest_median_s":5100.5,` +
			`"strategies":[{"strategy":["MEDIUM","HARD"],"median_race_time_s":5100.5,` +
			`"p10_race_time_s":5080.0,"p90_race_time_s":5130.0,"win_probability":0.42,"rank":1}]}`))
	}))
	defer server.Close()

	got, err := NewClient(server.URL).StrategySim(context.Background(),
		StrategySimRequest{TotalLaps: 53, TrackTempC: 30, FuelStartKg: 110, NSims: 500, Seed: 42})
	if err != nil {
		t.Fatalf("StrategySim: %v", err)
	}
	if !strings.Contains(body, `"total_laps":53`) {
		t.Errorf("request body = %q, want the laps field", body)
	}
	if len(got.Strategies) != 1 {
		t.Fatalf("got %d strategies, want 1", len(got.Strategies))
	}
	s := got.Strategies[0]
	if len(s.Strategy) != 2 || s.Strategy[0] != "MEDIUM" {
		t.Errorf("strategy = %v, want [MEDIUM HARD]", s.Strategy)
	}
	if s.WinProbability != 0.42 {
		t.Errorf("win probability = %v, want 0.42", s.WinProbability)
	}
	if s.P90RaceTimeS != 5130.0 {
		t.Errorf("p90 = %v, want 5130", s.P90RaceTimeS)
	}
}

// TestStrategySimValidatesBeforeSending means a bad form value never becomes a
// network round trip.
func TestStrategySimValidatesBeforeSending(t *testing.T) {
	_, err := NewClient("http://127.0.0.1:1").StrategySim(context.Background(),
		StrategySimRequest{TotalLaps: 999, TrackTempC: 30, FuelStartKg: 110, NSims: 500})
	if err == nil {
		t.Fatal("StrategySim sent an out-of-range request")
	}
}

// --- chat -------------------------------------------------------------------

// TestChatRejectsABlankQuestion avoids a guaranteed 422.
func TestChatRejectsABlankQuestion(t *testing.T) {
	if _, err := NewClient("http://127.0.0.1:1").Chat(context.Background(), ChatRequest{Message: "  "}); err == nil {
		t.Fatal("Chat accepted a blank message")
	}
}

// TestChatDecodesTheRetrievalTrace keeps the transparency panel populated: the
// trace is the reason this endpoint is interesting rather than a plain chatbot.
func TestChatDecodesTheRetrievalTrace(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"response":"Brake later into turn 4.","intent":"telemetry",` +
			`"entities":{},"sources":{"sql":2,"vector":1},"elapsed_ms":812,` +
			`"trace":{"path":"agent","tool_calls":["query_laps"],"iterations":2,` +
			`"sources":{"sql":2},"stages_ms":{"retrieve":300}}}`))
	}))
	defer server.Close()

	got, err := NewClient(server.URL).Chat(context.Background(), ChatRequest{Message: "where do I lose time?"})
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if got.Response == "" {
		t.Error("response is empty")
	}
	if got.Trace.Path != "agent" {
		t.Errorf("trace path = %q, want agent", got.Trace.Path)
	}
	if len(got.Trace.ToolCalls) != 1 || got.Trace.ToolCalls[0] != "query_laps" {
		t.Errorf("tool calls = %v, want [query_laps]", got.Trace.ToolCalls)
	}
	if got.Trace.Iterations != 2 {
		t.Errorf("iterations = %d, want 2", got.Trace.Iterations)
	}
}
