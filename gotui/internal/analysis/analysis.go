// Package analysis turns the API's raw comparison payloads into the ranked
// summaries the TUI draws.
//
// It holds no source of truth of its own: every number it reports is either
// taken straight from a service field or a documented difference between two of
// them. That matters because it is easy to over-claim here -- see the note on
// time loss in RankBySpeedDeficit.
package analysis

import (
	"fmt"
	"sort"
	"strings"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
)

// SectorNames are the three sector keys the service returns, in track order.
// The service builds them in this order in compare.py's _compute_sector_deltas.
var SectorNames = []string{"sector1_ms", "sector2_ms", "sector3_ms"}

// SectorDelta is one sector's time difference between two laps.
//
// DeltaMs is lap A minus lap B, so a POSITIVE value means lap A was SLOWER.
type SectorDelta struct {
	Name    string
	Index   int
	LapAMs  float64
	LapBMs  float64
	DeltaMs float64
	// Present is false when the service sent no time for either lap, which is
	// different from a genuine 0.000 difference.
	Present bool
}

// SectorDeltas differences the service's per-sector times.
//
// api.LapComparison.SectorDeltas is named "deltas" by the service but actually
// carries each lap's raw sector time ({"sector1_ms": [lapA, lapB]}), as its own
// docstring in compare.py states. The subtraction therefore has to happen here.
func SectorDeltas(raw map[string][]float64) []SectorDelta {
	out := make([]SectorDelta, 0, len(SectorNames))
	for i, name := range SectorNames {
		times := raw[name]
		if len(times) < 2 {
			out = append(out, SectorDelta{Name: name, Index: i + 1})
			continue
		}
		a, b := times[0], times[1]
		out = append(out, SectorDelta{
			Name:    name,
			Index:   i + 1,
			LapAMs:  a,
			LapBMs:  b,
			DeltaMs: a - b,
			// A zero on both sides is the service's "no time recorded" value
			// (compare.py writes 0.0 for a NULL sector), not a dead heat.
			Present: !(a == 0 && b == 0),
		})
	}
	return out
}

// WorstSector returns the sector where lap A lost the most time, and whether any
// sector was present at all.
func WorstSector(deltas []SectorDelta) (SectorDelta, bool) {
	var worst SectorDelta
	found := false
	for _, d := range deltas {
		if !d.Present {
			continue
		}
		if !found || d.DeltaMs > worst.DeltaMs {
			worst, found = d, true
		}
	}
	return worst, found
}

// Segment aggregates distance-aligned delta points into fixed-width buckets.
type Segment struct {
	StartM float64
	EndM   float64
	// MeanSpeedDelta is the average of lap A minus lap B, so negative means lap A
	// was slower through this stretch.
	MeanSpeedDelta float64
	// MinSpeedDelta is the single worst speed difference in the bucket, which is
	// what a driver actually feels (one bad corner is hidden by an average).
	MinSpeedDelta     float64
	MeanThrottleDelta float64
	MeanBrakeDelta    float64
	Points            int
}

// Segments buckets delta points by distance. binM is the bucket width; the
// service already samples every 10 m, so a 100 m bucket is ten points.
//
// A non-positive binM falls back to 100 m so a zero can never produce an
// infinite loop.
func Segments(deltas []api.DeltaPoint, binM float64) []Segment {
	if binM <= 0 {
		binM = 100
	}
	if len(deltas) == 0 {
		return nil
	}

	first := deltas[0].DistanceM
	out := []Segment{}
	cur := -1

	for _, p := range deltas {
		start := first + float64(int((p.DistanceM-first)/binM))*binM
		if cur < 0 || out[cur].StartM != start {
			out = append(out, Segment{StartM: start, EndM: start + binM, MinSpeedDelta: p.SpeedDelta})
			cur = len(out) - 1
		}
		out[cur].MeanSpeedDelta += p.SpeedDelta
		out[cur].MeanThrottleDelta += p.ThrottleDelta
		out[cur].MeanBrakeDelta += p.BrakeDelta
		if p.SpeedDelta < out[cur].MinSpeedDelta {
			out[cur].MinSpeedDelta = p.SpeedDelta
		}
		out[cur].Points++
	}

	for i := range out {
		if out[i].Points > 0 {
			n := float64(out[i].Points)
			out[i].MeanSpeedDelta /= n
			out[i].MeanThrottleDelta /= n
			out[i].MeanBrakeDelta /= n
		}
	}
	return out
}

// RankBySpeedDeficit orders segments worst-first by minimum speed delta.
//
// It deliberately does NOT call this "time lost". The service's delta payload
// carries speed, throttle, brake and steering differences only -- it has no
// per-point timestamp or absolute speed, so a real elapsed-time figure cannot be
// recovered from it. True time loss comes from SectorDeltas, which is built from
// the database's own sector times. Reporting a fabricated "seconds lost" here
// would be the most damaging kind of wrong: plausible and unfalsifiable.
func RankBySpeedDeficit(segments []Segment, topN int) []Segment {
	ranked := make([]Segment, len(segments))
	copy(ranked, segments)
	sort.SliceStable(ranked, func(i, j int) bool {
		return ranked[i].MinSpeedDelta < ranked[j].MinSpeedDelta
	})
	if topN > 0 && len(ranked) > topN {
		ranked = ranked[:topN]
	}
	return ranked
}

// BrakingSegments returns the buckets where lap A braked hardest relative to
// lap B, i.e. where lap A is giving away speed under braking.
func BrakingSegments(segments []Segment, topN int) []Segment {
	ranked := make([]Segment, 0, len(segments))
	for _, s := range segments {
		if s.MeanBrakeDelta < 0 {
			ranked = append(ranked, s)
		}
	}
	sort.SliceStable(ranked, func(i, j int) bool {
		return ranked[i].MeanBrakeDelta < ranked[j].MeanBrakeDelta
	})
	if topN > 0 && len(ranked) > topN {
		ranked = ranked[:topN]
	}
	return ranked
}

// SpeedRange reports the fastest and slowest speed delta across the segments,
// which sets the scale for the trace bars.
func SpeedRange(segments []Segment) (min, max float64) {
	if len(segments) == 0 {
		return 0, 0
	}
	min, max = segments[0].MeanSpeedDelta, segments[0].MeanSpeedDelta
	for _, s := range segments {
		if s.MeanSpeedDelta < min {
			min = s.MeanSpeedDelta
		}
		if s.MeanSpeedDelta > max {
			max = s.MeanSpeedDelta
		}
	}
	return min, max
}

// Bar renders value as a text bar of the given width, centred on zero.
//
// Half the cells are reserved for negatives and half for positives, so the bar
// shows sign by which side fills. A bar is used rather than a number alone
// because the whole point of the compare view is to see the shape of a lap at a
// glance. Labels are filled and empty cells are drawn as a lighter rune, so the
// full track length stays visible even when the value is zero.
func Bar(value, extent float64, width int, fill, empty string) string {
	if width <= 0 {
		return ""
	}
	// With no scale there is nothing to compare against, so draw no fill at all
	// rather than a bar that would read as "maximum" when it means "unknown".
	if extent <= 0 {
		return strings.Repeat(empty, width)
	}
	if value > extent {
		value = extent
	}
	if value < -extent {
		value = -extent
	}

	// Two runs, split so the callers always get exactly `width` cells: a
	// centred bar that renders width-1 cells would reintroduce the off-by-one
	// this whole file exists to avoid.
	negW := width / 2
	posW := width - negW

	var b strings.Builder
	if value >= 0 {
		scaled := scaledCells(value, extent, posW)
		b.WriteString(strings.Repeat(empty, negW))
		b.WriteString(strings.Repeat(fill, scaled))
		b.WriteString(strings.Repeat(empty, posW-scaled))
	} else {
		scaled := scaledCells(-value, extent, negW)
		b.WriteString(strings.Repeat(empty, negW-scaled))
		b.WriteString(strings.Repeat(fill, scaled))
		b.WriteString(strings.Repeat(empty, posW))
	}
	return b.String()
}

// scaledCells converts a magnitude into a cell count within room.
func scaledCells(value, extent float64, room int) int {
	if room <= 0 || extent <= 0 {
		return 0
	}
	scaled := int((value / extent) * float64(room))
	if scaled > room {
		return room
	}
	if scaled < 0 {
		return 0
	}
	return scaled
}

// ProgressBar renders a 0..1 fraction as a filled bar.
func ProgressBar(fraction float64, width int, fill, empty string) string {
	if width <= 0 {
		return ""
	}
	if fraction < 0 {
		fraction = 0
	}
	if fraction > 1 {
		fraction = 1
	}
	filled := int(fraction*float64(width) + 0.5)
	if filled > width {
		filled = width
	}
	return strings.Repeat(fill, filled) + strings.Repeat(empty, width-filled)
}

// FormatSector renders a sector duration.
//
// A sector is always shorter than a lap, so the m:ss.mmm form reads oddly for it
// (0:30.250). Under a minute it is shown in seconds, which is how sector times
// are conventionally quoted; anything longer falls back to the full form so an
// unusually long sector is never misreported.
func FormatSector(ms float64) string {
	if ms < 0 {
		return "--"
	}
	if ms < 60_000 {
		return fmt.Sprintf("%.3fs", ms/1000)
	}
	return FormatMillis(ms)
}

// FormatLapTime renders milliseconds as m:ss.mmm, matching how the frontend
// displays lap times. A nil or non-positive value is an em dash, never "0.000".
func FormatLapTime(ms *int) string {
	if ms == nil || *ms <= 0 {
		return "--"
	}
	return FormatMillis(float64(*ms))
}

// FormatMillis renders a millisecond duration as m:ss.mmm.
func FormatMillis(ms float64) string {
	if ms < 0 {
		return "--"
	}
	total := ms / 1000
	minutes := int(total / 60)
	seconds := total - float64(minutes*60)
	return fmt.Sprintf("%d:%06.3f", minutes, seconds)
}

// FormatDelta renders a signed millisecond difference, which reads better with
// an explicit sign than a bare number.
func FormatDelta(ms float64) string {
	return fmt.Sprintf("%+.3f", ms)
}

func abs(v float64) float64 {
	if v < 0 {
		return -v
	}
	return v
}

// Abs exposes the magnitude helper for callers that size a bar from a delta.
func Abs(v float64) float64 { return abs(v) }
