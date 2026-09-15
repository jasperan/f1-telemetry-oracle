package tui

import (
	"fmt"
	"strings"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/analysis"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
)

// This file is the non-interactive renderer: no styling, no escape sequences,
// fixed-width columns.
//
// It exists because the full-screen UI cannot be piped. A user running this in a
// cron job, over ssh without a TTY, or into `grep` needs the same numbers in a
// plain form, and a huh form attached to a pipe could never be answered anyway.

// PlainBar renders a centred delta bar using ASCII only, so it survives a pipe,
// a log file and a terminal without a Unicode font.
func PlainBar(value, extent float64, width int) string {
	return analysis.Bar(value, extent, width, "#", ".")
}

// PlainProgress renders a 0..1 fraction as an ASCII bar.
func PlainProgress(fraction float64, width int) string {
	return analysis.ProgressBar(fraction, width, "#", "-")
}

const plainRule = "--------------------------------------------------------------------------------"

// PlainComparison renders a lap comparison without styling.
//
// The two panels are deliberately labelled differently: the sector table comes
// from recorded times, while the speed panel is a derived difference and is not
// an elapsed time. Keeping that distinction visible in the plain output too stops
// a piped result from reading as if both were measured.
func PlainComparison(comparison *api.LapComparison, lapA, lapB string) string {
	if comparison == nil {
		return "no comparison available\n"
	}
	if len(comparison.LapIDs) >= 2 {
		lapA, lapB = comparison.LapIDs[0], comparison.LapIDs[1]
	}
	var b strings.Builder

	b.WriteString(fmt.Sprintf("lap comparison: %s (A) vs %s (B)\n", lapA, lapB))
	b.WriteString(plainRule + "\n")
	b.WriteString("SECTOR TIMES (recorded — this is real time)\n")
	// SectorDeltas always returns the three sector slots, marking an unrecorded
	// one as not-present, so there is no empty case to handle here.
	sectors := analysis.SectorDeltas(comparison.SectorDeltas)
	worst, hasWorst := analysis.WorstSector(sectors)
	for _, s := range sectors {
		if !s.Present {
			b.WriteString(fmt.Sprintf("  S%d  not recorded\n", s.Index))
			continue
		}
		marker := ""
		if hasWorst && s.Index == worst.Index && s.DeltaMs > 0 {
			marker = "   <-- biggest loss"
		}
		b.WriteString(fmt.Sprintf("  S%d  A %10s   B %10s   delta %10s ms%s\n",
			s.Index, analysis.FormatSector(s.LapAMs), analysis.FormatSector(s.LapBMs),
			analysis.FormatDelta(s.DeltaMs), marker))
	}
	b.WriteString("\n")
	b.WriteString("Positive delta means lap A was SLOWER in that sector.\n")

	b.WriteString("\n" + plainRule + "\n")
	b.WriteString("SPEED DELTA BY DISTANCE (derived — a speed difference, not an elapsed time)\n")
	segments := analysis.Segments(comparison.Deltas, 100)
	if len(segments) == 0 {
		b.WriteString("  no distance-aligned telemetry returned for these laps\n")
		return b.String()
	}
	_, maxAbs := analysis.SpeedRange(segments)
	if maxAbs < 0 {
		maxAbs = -maxAbs
	}
	for _, s := range segments {
		b.WriteString(fmt.Sprintf("  %6.0fm-%6.0fm  %s  %+7.2f km/h\n",
			s.StartM, s.EndM, PlainBar(s.MeanSpeedDelta, maxAbs, 24), s.MeanSpeedDelta))
	}

	b.WriteString("\n" + plainRule + "\n")
	b.WriteString("WHERE YOU LOSE THE MOST SPEED (ranked by worst deficit in each 100 m)\n")
	for i, s := range analysis.RankBySpeedDeficit(segments, 6) {
		b.WriteString(fmt.Sprintf("  %d. %6.0fm-%6.0fm  %+7.2f km/h\n", i+1, s.StartM, s.EndM, s.MinSpeedDelta))
	}

	if braking := analysis.BrakingSegments(segments, 5); len(braking) > 0 {
		b.WriteString("\n" + plainRule + "\n")
		b.WriteString("BRAKING LOSSES (stretches where lap A brakes harder)\n")
		for i, s := range braking {
			b.WriteString(fmt.Sprintf("  %d. %6.0fm-%6.0fm  brake %+7.2f\n", i+1, s.StartM, s.EndM, s.MeanBrakeDelta))
		}
	}
	return b.String()
}

// PlainSimVsReal renders the auto-matched comparison.
func PlainSimVsReal(result *api.SimVsReal) string {
	if result == nil {
		return "no comparison available\n"
	}
	var b strings.Builder
	b.WriteString(fmt.Sprintf("sim lap:  %s\n", result.SimLapID))
	b.WriteString(fmt.Sprintf("real lap: %s\n", result.RealLapID))
	b.WriteString(fmt.Sprintf("circuit:  %s\n\n", result.CircuitID))
	b.WriteString(PlainComparison(&result.Comparison, result.SimLapID, result.RealLapID))
	return b.String()
}

// PlainCircuits renders the circuit list as fixed-width columns.
func PlainCircuits(circuits []api.Circuit) string {
	if len(circuits) == 0 {
		return "no circuits returned\n"
	}
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%-22s %-40s %-18s %s\n", "id", "name", "country", "length"))
	for _, c := range circuits {
		length := "--"
		if c.TrackLengthM != nil {
			length = fmt.Sprintf("%.0f m", *c.TrackLengthM)
		}
		b.WriteString(fmt.Sprintf("%-22s %-40s %-18s %s\n", c.CircuitID, c.DisplayName(), c.Country, length))
	}
	return b.String()
}

// PlainSessions renders the session list.
func PlainSessions(sessions []api.Session) string {
	if len(sessions) == 0 {
		return "no sessions returned\n"
	}
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%-28s %-12s %-10s %-22s %s\n", "session", "type", "source", "circuit", "season"))
	for _, s := range sessions {
		season := "--"
		if s.Season != nil {
			season = fmt.Sprintf("%d", *s.Season)
		}
		b.WriteString(fmt.Sprintf("%-28s %-12s %-10s %-22s %s\n", s.SessionID, s.SessionType, s.Source, s.CircuitID, season))
	}
	return b.String()
}

// PlainLaps renders the lap list.
func PlainLaps(laps []api.Lap) string {
	if len(laps) == 0 {
		return "no laps returned\n"
	}
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%-28s %-18s %5s  %-10s %-10s %s\n", "lap", "driver", "no.", "lap time", "tyre", "status"))
	for _, l := range laps {
		compound := "--"
		if l.TireCompound != nil {
			compound = *l.TireCompound
		}
		status := "invalid"
		if l.IsValid {
			status = "valid"
		}
		b.WriteString(fmt.Sprintf("%-28s %-18s %5d  %-10s %-10s %s\n",
			l.LapID, l.DriverID, l.LapNumber, analysis.FormatLapTime(l.LapTimeMs), compound, status))
	}
	return b.String()
}

// PlainTwin renders the driving-style match.
func PlainTwin(twin *api.DrivingTwin) string {
	if twin == nil {
		return "no analysis available\n"
	}
	if twin.Error != "" {
		return "the service reported: " + twin.Error + "\n"
	}
	var b strings.Builder
	if twin.OverallTwin != nil {
		b.WriteString(fmt.Sprintf("you drive like %s (mean cosine distance %.4f, lower is closer)\n\n",
			twin.OverallTwin.DriverCode, twin.OverallTwin.MeanSimilarity))
	} else {
		b.WriteString("no aggregated twin could be computed\n\n")
	}
	for _, sector := range twin.Sectors {
		b.WriteString(fmt.Sprintf("SECTOR %d\n", sector.Sector))
		if len(sector.Matches) == 0 {
			b.WriteString("  no comparable real laps in this sector\n")
			continue
		}
		for _, m := range sector.Matches {
			b.WriteString(fmt.Sprintf("  %-24s %-6s distance %.4f\n", m.Driver, m.Code, m.Similarity))
		}
	}
	return b.String()
}

// PlainStrategy renders the ranked strategies.
func PlainStrategy(sim *api.StrategySim) string {
	if sim == nil {
		return "no simulation available\n"
	}
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%d laps · %d sims · track %.0f C\n\n", sim.TotalLaps, sim.NSims, sim.TrackTempC))
	b.WriteString(fmt.Sprintf("%4s  %-26s %10s %10s %10s  %s\n", "rank", "strategy", "median", "p10", "p90", "win probability"))
	for _, s := range sim.Strategies {
		b.WriteString(fmt.Sprintf("%4d  %-26s %10s %10s %10s  %s %.0f%%\n",
			s.Rank, strings.Join(s.Strategy, " -> "),
			analysis.FormatMillis(s.MedianRaceTimeS*1000),
			analysis.FormatMillis(s.P10RaceTimeS*1000),
			analysis.FormatMillis(s.P90RaceTimeS*1000),
			PlainProgress(s.WinProbability, 12), s.WinProbability*100))
	}
	b.WriteString("\nwin probability is this strategy's share of simulated wins, not a prediction of the real race\n")
	return b.String()
}

// PlainChat renders an answer with its retrieval trace.
func PlainChat(chat *api.ChatResponse) string {
	if chat == nil {
		return "no answer available\n"
	}
	var b strings.Builder
	b.WriteString(chat.Response)
	b.WriteString("\n\n" + plainRule + "\n")
	b.WriteString(fmt.Sprintf("path %s", chat.Trace.Path))
	if chat.Intent != "" {
		b.WriteString(fmt.Sprintf(" · intent %s", chat.Intent))
	}
	b.WriteString(fmt.Sprintf(" · %d ms\n", chat.ElapsedMs))
	if len(chat.Trace.ToolCalls) > 0 {
		b.WriteString("tools: " + strings.Join(chat.Trace.ToolCalls, ", ") + "\n")
	}
	for _, source := range sortedKeys(chat.Sources) {
		b.WriteString(fmt.Sprintf("  %s: %d\n", source, chat.Sources[source]))
	}
	return b.String()
}

// sortedKeys keeps the trace output stable, because a Go map iterates in a
// random order and an unstable diff would make the piped output noisy.
func sortedKeys(m map[string]int) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	for i := 1; i < len(keys); i++ {
		for j := i; j > 0 && keys[j] < keys[j-1]; j-- {
			keys[j], keys[j-1] = keys[j-1], keys[j]
		}
	}
	return keys
}

// PlainHealth renders the health check.
func PlainHealth(baseURL string, health *api.HealthResponse) string {
	status := "unknown"
	if health != nil && health.Status != "" {
		status = health.Status
	}
	return fmt.Sprintf("api %s: %s\n", baseURL, status)
}
