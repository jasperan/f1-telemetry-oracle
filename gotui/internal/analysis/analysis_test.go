package analysis

import (
	"strings"
	"testing"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
)

// --- sector deltas ----------------------------------------------------------

// TestSectorDeltasDifferencesTheRawTimes is the regression guard for the
// service's misleading field name: SectorDeltas holds raw per-lap times, not
// differences, so the sign convention has to be produced here.
func TestSectorDeltasDifferencesTheRawTimes(t *testing.T) {
	raw := map[string][]float64{
		"sector1_ms": {30000, 29500}, // lap A slower by 500
		"sector2_ms": {28000, 28400}, // lap A faster by 400
		"sector3_ms": {25000, 25000}, // dead heat
	}
	got := SectorDeltas(raw)

	if len(got) != 3 {
		t.Fatalf("got %d sectors, want 3", len(got))
	}
	if got[0].Name != "sector1_ms" || got[0].Index != 1 {
		t.Errorf("first sector = %q/%d, want sector1_ms/1", got[0].Name, got[0].Index)
	}
	if got[0].DeltaMs != 500 {
		t.Errorf("sector1 delta = %v, want +500 (lap A slower)", got[0].DeltaMs)
	}
	if got[1].DeltaMs != -400 {
		t.Errorf("sector2 delta = %v, want -400 (lap A faster)", got[1].DeltaMs)
	}
	if got[2].DeltaMs != 0 {
		t.Errorf("sector3 delta = %v, want 0", got[2].DeltaMs)
	}
	for _, d := range got {
		if !d.Present {
			t.Errorf("%s: Present = false, want true", d.Name)
		}
	}
}

// TestSectorDeltasTreatsDoubleZeroAsMissing pins the NULL convention: compare.py
// writes 0.0 for a NULL sector, so 0/0 means "not recorded", not a dead heat.
func TestSectorDeltasTreatsDoubleZeroAsMissing(t *testing.T) {
	got := SectorDeltas(map[string][]float64{
		"sector1_ms": {0, 0},
		"sector2_ms": {1000, 0},
	})
	if got[0].Present {
		t.Error("0/0 reported as Present, want missing")
	}
	if !got[1].Present {
		t.Error("1000/0 reported as missing, want present (a real 1000 ms gap)")
	}
}

// TestSectorDeltasHandlesMissingSectors keeps a short list from panicking.
func TestSectorDeltasHandlesMissingSectors(t *testing.T) {
	got := SectorDeltas(map[string][]float64{"sector1_ms": {30000}})
	if len(got) != 3 {
		t.Fatalf("got %d sectors, want 3", len(got))
	}
	if got[0].Present {
		t.Error("a single time cannot yield a delta, want Present=false")
	}
	if got[2].Name != "sector3_ms" {
		t.Errorf("third sector = %q, want sector3_ms", got[2].Name)
	}
}

// TestWorstSectorPicksTheBiggestLoss ignores sectors with no data.
func TestWorstSectorPicksTheBiggestLoss(t *testing.T) {
	deltas := []SectorDelta{
		{Name: "sector1_ms", DeltaMs: 120, Present: true},
		{Name: "sector2_ms", DeltaMs: 0, Present: false},
		{Name: "sector3_ms", DeltaMs: 480, Present: true},
	}
	worst, ok := WorstSector(deltas)
	if !ok {
		t.Fatal("WorstSector reported nothing")
	}
	if worst.Name != "sector3_ms" || worst.DeltaMs != 480 {
		t.Errorf("worst = %s/%v, want sector3_ms/480", worst.Name, worst.DeltaMs)
	}
}

// TestWorstSectorReportsNothingWhenAllMissing keeps a blank comparison silent.
func TestWorstSectorReportsNothingWhenAllMissing(t *testing.T) {
	if _, ok := WorstSector([]SectorDelta{{Name: "sector1_ms"}}); ok {
		t.Error("WorstSector found a sector in an empty comparison")
	}
}

// --- segment bucketing ------------------------------------------------------

func deltaPoint(distance, speed, throttle, brake float64) api.DeltaPoint {
	return api.DeltaPoint{DistanceM: distance, SpeedDelta: speed, ThrottleDelta: throttle, BrakeDelta: brake}
}

// TestSegmentsBucketsByDistance checks binning, means and the per-bucket minimum.
func TestSegmentsBucketsByDistance(t *testing.T) {
	points := []api.DeltaPoint{
		deltaPoint(0, -10, -5, -2),
		deltaPoint(10, -20, -5, -2),
		deltaPoint(100, 6, 1, 0),
		deltaPoint(150, 4, 1, 0),
	}
	got := Segments(points, 100)

	if len(got) != 2 {
		t.Fatalf("got %d segments, want 2", len(got))
	}
	if got[0].StartM != 0 || got[0].EndM != 100 {
		t.Errorf("first segment = [%v,%v), want [0,100)", got[0].StartM, got[0].EndM)
	}
	if got[0].Points != 2 {
		t.Errorf("first segment has %d points, want 2", got[0].Points)
	}
	if got[0].MeanSpeedDelta != -15 {
		t.Errorf("first mean = %v, want -15", got[0].MeanSpeedDelta)
	}
	// The minimum is the whole point: a mean hides the single bad corner.
	if got[0].MinSpeedDelta != -20 {
		t.Errorf("first min = %v, want -20", got[0].MinSpeedDelta)
	}
	if got[1].MeanSpeedDelta != 5 {
		t.Errorf("second mean = %v, want 5", got[1].MeanSpeedDelta)
	}
	if got[1].MinSpeedDelta != 4 {
		t.Errorf("second min = %v, want 4", got[1].MinSpeedDelta)
	}
}

// TestSegmentsOffsetsFromTheFirstPoint keeps a lap that starts mid-track grouped
// by its own distance rather than by raw multiples of the bin width.
func TestSegmentsOffsetsFromTheFirstPoint(t *testing.T) {
	got := Segments([]api.DeltaPoint{
		deltaPoint(30, 1, 0, 0),
		deltaPoint(40, 1, 0, 0),
		deltaPoint(130, 1, 0, 0),
	}, 100)
	if len(got) != 2 {
		t.Fatalf("got %d segments, want 2 (bins start at 30, not 0)", len(got))
	}
	if got[0].StartM != 30 {
		t.Errorf("first bin starts at %v, want 30", got[0].StartM)
	}
}

// TestSegmentsRejectsAZeroBinWidth guards the infinite-loop case.
func TestSegmentsRejectsAZeroBinWidth(t *testing.T) {
	got := Segments([]api.DeltaPoint{deltaPoint(0, 1, 0, 0), deltaPoint(50, 1, 0, 0)}, 0)
	if len(got) != 1 {
		t.Fatalf("got %d segments, want 1 with the 100 m fallback", len(got))
	}
}

// TestSegmentsEmptyInputIsNil keeps an absent comparison from panicking.
func TestSegmentsEmptyInputIsNil(t *testing.T) {
	if got := Segments(nil, 100); got != nil {
		t.Errorf("Segments(nil) = %v, want nil", got)
	}
}

// --- ranking ----------------------------------------------------------------

// TestRankBySpeedDeficitIsWorstFirst pins the ordering the UI relies on.
func TestRankBySpeedDeficitIsWorstFirst(t *testing.T) {
	segments := []Segment{
		{StartM: 0, MinSpeedDelta: -3},
		{StartM: 100, MinSpeedDelta: -22},
		{StartM: 200, MinSpeedDelta: 8},
	}
	got := RankBySpeedDeficit(segments, 2)
	if len(got) != 2 {
		t.Fatalf("got %d ranked segments, want 2", len(got))
	}
	if got[0].StartM != 100 {
		t.Errorf("worst segment starts at %v, want 100", got[0].StartM)
	}
	if got[1].StartM != 0 {
		t.Errorf("second segment starts at %v, want 0", got[1].StartM)
	}
	// The input order must survive: the caller still draws the full trace.
	if segments[0].StartM != 0 {
		t.Error("RankBySpeedDeficit reordered its input slice")
	}
}

// TestRankBySpeedDeficitZeroTopNReturnsAll documents the "no limit" convention.
func TestRankBySpeedDeficitZeroTopNReturnsAll(t *testing.T) {
	segments := []Segment{{MinSpeedDelta: -1}, {MinSpeedDelta: -2}}
	if got := RankBySpeedDeficit(segments, 0); len(got) != 2 {
		t.Errorf("got %d, want all 2", len(got))
	}
}

// TestBrakingSegmentsKeepsOnlyLosses means only stretches where lap A brakes
// harder appear, so the panel never lists a gain as a problem.
func TestBrakingSegmentsKeepsOnlyLosses(t *testing.T) {
	segments := []Segment{
		{StartM: 0, MeanBrakeDelta: -4},
		{StartM: 100, MeanBrakeDelta: 2},
		{StartM: 200, MeanBrakeDelta: -9},
	}
	got := BrakingSegments(segments, 5)
	if len(got) != 2 {
		t.Fatalf("got %d braking segments, want 2", len(got))
	}
	if got[0].StartM != 200 {
		t.Errorf("hardest braking starts at %v, want 200", got[0].StartM)
	}
}

// TestSpeedRangeSetsTheBarScale covers the empty case as well as a real span.
func TestSpeedRangeSetsTheBarScale(t *testing.T) {
	if min, max := SpeedRange(nil); min != 0 || max != 0 {
		t.Errorf("SpeedRange(nil) = %v,%v want 0,0", min, max)
	}
	min, max := SpeedRange([]Segment{{MeanSpeedDelta: -12}, {MeanSpeedDelta: 7}})
	if min != -12 || max != 7 {
		t.Errorf("SpeedRange = %v,%v want -12,7", min, max)
	}
}

// --- rendering --------------------------------------------------------------

// TestBarIsAlwaysExactlyAsWideAsAsked is the off-by-one guard: a centred bar
// that rendered width-1 cells was a real bug in the sibling implementation.
func TestBarIsAlwaysExactlyAsWideAsAsked(t *testing.T) {
	for width := 1; width <= 41; width++ {
		for _, value := range []float64{-10, -3, 0, 3, 10, 100, -100} {
			got := Bar(value, 10, width, "#", ".")
			if len([]rune(got)) != width {
				t.Fatalf("Bar(%v, 10, %d) rendered %d cells, want %d: %q",
					value, width, len([]rune(got)), width, got)
			}
		}
	}
}

// TestBarDrawsNegativesLeftOfCentreAndPositivesRight makes the sign readable at
// a glance, which is the reason this is a bar and not a number.
func TestBarDrawsNegativesLeftOfCentreAndPositivesRight(t *testing.T) {
	neg := Bar(-10, 10, 10, "#", ".")
	if neg != "#####....." {
		t.Errorf("negative bar = %q, want %q", neg, "#####.....")
	}
	pos := Bar(10, 10, 10, "#", ".")
	if pos != ".....#####" {
		t.Errorf("positive bar = %q, want %q", pos, ".....#####")
	}
	zero := Bar(0, 10, 10, "#", ".")
	if zero != ".........." {
		t.Errorf("empty bar = %q, want all empty cells", zero)
	}
}

// TestBarClampsBeyondTheExtent stops an outlier from overflowing the row.
func TestBarClampsBeyondTheExtent(t *testing.T) {
	if got := Bar(1e9, 10, 8, "#", "."); got != "....####" {
		t.Errorf("clamped positive bar = %q, want %q", got, "....####")
	}
	if got := Bar(-1e9, 10, 8, "#", "."); got != "####...." {
		t.Errorf("clamped negative bar = %q, want %q", got, "####....")
	}
}

// TestBarHandlesDegenerateArguments keeps a zero extent from dividing by zero.
func TestBarHandlesDegenerateArguments(t *testing.T) {
	if got := Bar(5, 0, 6, "#", "."); got != "......" {
		t.Errorf("zero extent bar = %q, want all empty", got)
	}
	if got := Bar(5, 10, 0, "#", "."); got != "" {
		t.Errorf("zero width bar = %q, want empty string", got)
	}
}

// TestProgressBarFillsProportionally rounds rather than truncates.
func TestProgressBarFillsProportionally(t *testing.T) {
	if got := ProgressBar(0.5, 10, "#", "."); got != "#####....." {
		t.Errorf("half = %q, want %q", got, "#####.....")
	}
	if got := ProgressBar(0, 4, "#", "."); got != "...." {
		t.Errorf("zero = %q, want %q", got, "....")
	}
	if got := ProgressBar(1, 4, "#", "."); got != "####" {
		t.Errorf("full = %q, want %q", got, "####")
	}
	// Out-of-range fractions must clamp, not panic or overflow the row.
	if got := ProgressBar(5, 4, "#", "."); got != "####" {
		t.Errorf("over-full = %q, want %q", got, "####")
	}
	if got := ProgressBar(-5, 4, "#", "."); got != "...." {
		t.Errorf("negative = %q, want %q", got, "....")
	}
}

// TestProgressBarIsExactlyAsWideAsAsked mirrors the Bar guard.
func TestProgressBarIsExactlyAsWideAsAsked(t *testing.T) {
	for width := 1; width <= 30; width++ {
		for _, f := range []float64{0, 0.01, 0.33, 0.5, 0.99, 1} {
			got := ProgressBar(f, width, "#", ".")
			if len([]rune(got)) != width {
				t.Fatalf("ProgressBar(%v, %d) rendered %d cells, want %d",
					f, width, len([]rune(got)), width)
			}
		}
	}
}

// --- formatting -------------------------------------------------------------

// TestFormatLapTimeMatchesTheFrontend covers the m:ss.mmm shape and the NULL case.
func TestFormatLapTimeMatchesTheFrontend(t *testing.T) {
	ms := 83456
	if got := FormatLapTime(&ms); got != "1:23.456" {
		t.Errorf("FormatLapTime(83456) = %q, want %q", got, "1:23.456")
	}
	if got := FormatLapTime(nil); got != "--" {
		t.Errorf("FormatLapTime(nil) = %q, want %q", got, "--")
	}
	zero := 0
	if got := FormatLapTime(&zero); got != "--" {
		t.Errorf("FormatLapTime(0) = %q, want %q (0 means not recorded)", got, "--")
	}
}

// TestFormatMillisPadsSeconds keeps the decimal point aligned across values.
func TestFormatMillisPadsSeconds(t *testing.T) {
	cases := map[float64]string{
		0:     "0:00.000",
		1234:  "0:01.234",
		60000: "1:00.000",
	}
	for in, want := range cases {
		if got := FormatMillis(in); got != want {
			t.Errorf("FormatMillis(%v) = %q, want %q", in, got, want)
		}
	}
	if got := FormatMillis(-1); got != "--" {
		t.Errorf("FormatMillis(-1) = %q, want %q", got, "--")
	}
}

// TestFormatSectorUsesSecondsBelowAMinute keeps a sub-minute sector readable
// instead of quoting it as 0:ss.mmm.
func TestFormatSectorUsesSecondsBelowAMinute(t *testing.T) {
	cases := map[float64]string{
		30250: "30.250s",
		41480: "41.480s",
		0:     "0.000s",
	}
	for in, want := range cases {
		if got := FormatSector(in); got != want {
			t.Errorf("FormatSector(%v) = %q, want %q", in, got, want)
		}
	}
	// Above a minute the full form is used, so an unusually long sector is not
	// silently rendered as an impossible number of seconds.
	if got := FormatSector(75000); got != "1:15.000" {
		t.Errorf("FormatSector(75000) = %q, want %q", got, "1:15.000")
	}
	if got := FormatSector(-1); got != "--" {
		t.Errorf("FormatSector(-1) = %q, want %q", got, "--")
	}
}

// TestFormatDeltaAlwaysCarriesASign means a gain is never mistaken for a loss.
func TestFormatDeltaAlwaysCarriesASign(t *testing.T) {
	if got := FormatDelta(120); !strings.HasPrefix(got, "+") {
		t.Errorf("FormatDelta(120) = %q, want a leading +", got)
	}
	if got := FormatDelta(-120); !strings.HasPrefix(got, "-") {
		t.Errorf("FormatDelta(-120) = %q, want a leading -", got)
	}
}
