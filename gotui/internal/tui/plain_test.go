package tui

import (
	"strings"
	"testing"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
)

// TestPlainOutputCarriesNoEscapeSequences is the contract of this renderer: it
// has to survive a pipe, a log file and a terminal without Unicode.
func TestPlainOutputCarriesNoEscapeSequences(t *testing.T) {
	samples := map[string]string{
		"circuits": PlainCircuits([]api.Circuit{{CircuitID: "bahrain", CircuitName: "Bahrain", Country: "Bahrain"}}),
		"sessions": PlainSessions([]api.Session{{SessionID: "s1", SessionType: "race", Source: "sim", CircuitID: "bahrain"}}),
		"laps":     PlainLaps([]api.Lap{{LapID: "l1", DriverID: "VER", LapNumber: 1}}),
		"compare":  PlainComparison(sampleComparison(), "a", "b"),
		"twin":     PlainTwin(&api.DrivingTwin{OverallTwin: &api.TwinDriver{DriverCode: "VER", MeanSimilarity: 0.1}}),
		"strategy": PlainStrategy(&api.StrategySim{TotalLaps: 53, NSims: 500, Strategies: []api.StrategySimStrategy{
			{Strategy: []string{"MEDIUM"}, MedianRaceTimeS: 5100, WinProbability: 0.4, Rank: 1},
		}}),
		"chat":   PlainChat(&api.ChatResponse{Response: "Brake later.", Trace: api.RetrievalTrace{Path: "agent"}}),
		"health": PlainHealth("http://127.0.0.1:8100", &api.HealthResponse{Status: "ok"}),
	}
	for name, out := range samples {
		if out == "" {
			t.Errorf("%s rendered nothing", name)
		}
		if strings.Contains(out, "\x1b") {
			t.Errorf("%s contains an escape sequence, so it cannot be piped: %q", name, out)
		}
	}
}

// sampleComparison is a small but complete comparison payload.
func sampleComparison() *api.LapComparison {
	return &api.LapComparison{
		LapIDs: []string{"a", "b"},
		Deltas: []api.DeltaPoint{
			{DistanceM: 0, SpeedDelta: -12.5, ThrottleDelta: -4, BrakeDelta: -2},
			{DistanceM: 10, SpeedDelta: -20, ThrottleDelta: -4, BrakeDelta: -2},
			{DistanceM: 110, SpeedDelta: 6, ThrottleDelta: 1, BrakeDelta: 0},
		},
		SectorDeltas: map[string][]float64{
			"sector1_ms": {30000, 29500},
			"sector2_ms": {28000, 28400},
		},
	}
}

// TestPlainComparisonLabelsTheTwoKindsOfEvidence keeps a piped result from being
// misread: the sector table is recorded time, the speed panel is a difference.
func TestPlainComparisonLabelsTheTwoKindsOfEvidence(t *testing.T) {
	out := PlainComparison(sampleComparison(), "a", "b")
	for _, want := range []string{
		"recorded",
		"real time",
		"derived",
		"not an elapsed time",
		"SLOWER",
		"biggest loss",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("plain comparison is missing %q:\n%s", want, out)
		}
	}
}

// TestPlainComparisonReportsTheWorstSector means the headline number matches the
// arithmetic: sector 1 is 500 ms slower for lap A, sector 2 is 400 ms faster.
func TestPlainComparisonReportsTheWorstSector(t *testing.T) {
	out := PlainComparison(sampleComparison(), "a", "b")
	if !strings.Contains(out, "+500.000") {
		t.Errorf("the sector-1 delta is missing from:\n%s", out)
	}
	if !strings.Contains(out, "-400.000") {
		t.Errorf("the sector-2 gain is missing from:\n%s", out)
	}
	if !strings.Contains(out, "S1") || !strings.Contains(out, "S3") {
		t.Errorf("all three sectors should be listed even when one has no time:\n%s", out)
	}
}

// TestPlainComparisonHandlesNoComparison keeps an empty payload printable.
func TestPlainComparisonHandlesNoComparison(t *testing.T) {
	if got := PlainComparison(nil, "a", "b"); !strings.Contains(got, "no comparison") {
		t.Errorf("PlainComparison(nil) = %q", got)
	}
	empty := PlainComparison(&api.LapComparison{LapIDs: []string{"a", "b"}}, "a", "b")
	// SectorDeltas always yields the three slots, so an unrecorded sector is
	// reported per slot rather than as a missing table.
	if !strings.Contains(empty, "not recorded") {
		t.Errorf("an empty comparison should mark its sectors unrecorded: %q", empty)
	}
	if !strings.Contains(empty, "no distance-aligned telemetry") {
		t.Errorf("an empty delta list should say so: %q", empty)
	}
}

// TestPlainSimVsRealNamesBothLaps keeps the match readable.
func TestPlainSimVsRealNamesBothLaps(t *testing.T) {
	out := PlainSimVsReal(&api.SimVsReal{
		SimLapID:   "sim_1",
		RealLapID:  "real_9",
		CircuitID:  "bahrain",
		Comparison: *sampleComparison(),
	})
	for _, want := range []string{"sim_1", "real_9", "bahrain"} {
		if !strings.Contains(out, want) {
			t.Errorf("plain sim-vs-real is missing %q:\n%s", want, out)
		}
	}
}

// TestPlainStrategyStatesTheWinProbabilityCaveat stops a share of simulated wins
// from reading as a forecast.
func TestPlainStrategyStatesTheWinProbabilityCaveat(t *testing.T) {
	out := PlainStrategy(&api.StrategySim{
		TotalLaps: 53, NSims: 500, FastestMedianS: 5100,
		Strategies: []api.StrategySimStrategy{
			{Strategy: []string{"MEDIUM", "HARD"}, MedianRaceTimeS: 5100, P10RaceTimeS: 5080, P90RaceTimeS: 5130, WinProbability: 0.42, Rank: 1},
		},
	})
	if !strings.Contains(out, "not a prediction") {
		t.Errorf("the strategy output does not qualify win probability:\n%s", out)
	}
	if !strings.Contains(out, "MEDIUM -> HARD") {
		t.Errorf("the strategy names are missing:\n%s", out)
	}
	// 5100 seconds is a realistic full-race median, rendered as m:ss.mmm.
	if !strings.Contains(out, "85:00.000") {
		t.Errorf("the median should be rendered as m:ss.mmm:\n%s", out)
	}
}

// TestPlainTwinSurfacesAServiceError keeps a partial result honest rather than
// printing an empty panel.
func TestPlainTwinSurfacesAServiceError(t *testing.T) {
	out := PlainTwin(&api.DrivingTwin{Error: "Not enough telemetry frames"})
	if !strings.Contains(out, "Not enough telemetry frames") {
		t.Errorf("the service's error was swallowed: %q", out)
	}
	if got := PlainTwin(nil); !strings.Contains(got, "no analysis") {
		t.Errorf("PlainTwin(nil) = %q", got)
	}
}

// TestPlainChatIsStableAcrossRuns guards against map iteration order leaking into
// piped output, which would make a diff noisy.
func TestPlainChatIsStableAcrossRuns(t *testing.T) {
	chat := &api.ChatResponse{
		Response: "answer",
		Sources:  map[string]int{"vector": 1, "sql": 2, "graph": 3},
		Trace:    api.RetrievalTrace{Path: "rag"},
	}
	first := PlainChat(chat)
	for i := 0; i < 20; i++ {
		if got := PlainChat(chat); got != first {
			t.Fatalf("output changed between runs:\n%s\n---\n%s", first, got)
		}
	}
	if !strings.Contains(first, "graph: 3") {
		t.Errorf("source counts are missing:\n%s", first)
	}
	// Sources must be ordered, not random.
	if strings.Index(first, "graph") > strings.Index(first, "sql") {
		t.Errorf("sources are not sorted:\n%s", first)
	}
}

// TestPlainHealthReportsTheStatus covers the cheapest endpoint.
func TestPlainHealthReportsTheStatus(t *testing.T) {
	if got := PlainHealth("http://x", &api.HealthResponse{Status: "ok"}); !strings.Contains(got, "ok") {
		t.Errorf("PlainHealth = %q", got)
	}
	if got := PlainHealth("http://x", nil); !strings.Contains(got, "unknown") {
		t.Errorf("PlainHealth(nil) = %q, want an explicit unknown", got)
	}
}

// TestPlainEmptyListsSaySo keeps an empty result from looking like a crash.
func TestPlainEmptyListsSaySo(t *testing.T) {
	for name, out := range map[string]string{
		"circuits": PlainCircuits(nil),
		"sessions": PlainSessions(nil),
		"laps":     PlainLaps(nil),
	} {
		if !strings.Contains(out, "no ") {
			t.Errorf("%s on empty input rendered %q, want an explanatory line", name, out)
		}
	}
}
