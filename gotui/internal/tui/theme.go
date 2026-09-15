package tui

import (
	"strconv"
	"strings"

	"charm.land/lipgloss/v2"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/analysis"
)

// Design tokens — the project-wide "Premium Dark-Tech" set.
//
// Source of truth: docs/tui-design-tokens.md. These 14 values are the only
// colours allowed in TUI source, and scripts/tui-shot/check_palette.py enforces
// it by scanning this file's text, comments included.
const (
	hexBG        = "#1e1e2e" // bg
	hexSurface   = "#181825" // surface
	hexElevated  = "#313244" // elevated
	hexHighest   = "#45475a" // highest
	hexText      = "#cdd6f4" // text
	hexSubtext   = "#a6adc8" // subtext
	hexMuted     = "#6c7086" // muted
	hexDim       = "#585b70" // dim
	hexPrimary   = "#89b4fa" // primary
	hexSecondary = "#cba6f7" // secondary
	hexInfo      = "#89dceb" // info
	hexSuccess   = "#a6e3a1" // success
	hexWarning   = "#f9e2af" // warning
	hexError     = "#f38ba8" // error
)

// Bar runes. A filled cell is a block; an empty cell is a light dot so the full
// lap distance stays visible even where the delta is zero.
const (
	barFill  = "█"
	barEmpty = "·"
)

var (
	colBG       = lipgloss.Color(hexBG)
	colSurface  = lipgloss.Color(hexSurface)
	colElevated = lipgloss.Color(hexElevated)
	colHighest  = lipgloss.Color(hexHighest)
	colText     = lipgloss.Color(hexText)
	colSubtext  = lipgloss.Color(hexSubtext)
	colMuted    = lipgloss.Color(hexMuted)
	colDim      = lipgloss.Color(hexDim)
	colPrimary  = lipgloss.Color(hexPrimary)
	colInfo     = lipgloss.Color(hexInfo)
	colSuccess  = lipgloss.Color(hexSuccess)
	colWarning  = lipgloss.Color(hexWarning)
	colError    = lipgloss.Color(hexError)
)

// MinWidth is the narrowest terminal the full-screen UI will draw for. Below it
// the app falls back to the plain renderer, rather than wrapping every character
// onto its own line.
const MinWidth = 20

var (
	styleTitle    = lipgloss.NewStyle().Bold(true).Foreground(colPrimary)
	styleSubtitle = lipgloss.NewStyle().Foreground(colSubtext)
	styleMuted    = lipgloss.NewStyle().Foreground(colMuted)
	styleDim      = lipgloss.NewStyle().Foreground(colDim)
	styleText     = lipgloss.NewStyle().Foreground(colText)
	styleInfo     = lipgloss.NewStyle().Foreground(colInfo)
	styleSuccess  = lipgloss.NewStyle().Foreground(colSuccess)
	styleWarning  = lipgloss.NewStyle().Foreground(colWarning)
	styleError    = lipgloss.NewStyle().Foreground(colError)

	// Selection is inverted: accent background, dark text, bold.
	styleSelected = lipgloss.NewStyle().Bold(true).Foreground(colBG).Background(colPrimary)

	// Focus is a border colour change, never a thickness change.
	stylePane      = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(colDim).Padding(0, 1)
	stylePaneFocus = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(colPrimary).Padding(0, 1)
	styleStatusBar = lipgloss.NewStyle().Background(colSurface).Foreground(colText).Padding(0, 1)
	styleKeyHint   = lipgloss.NewStyle().Foreground(colSubtext)
	styleKeyGlyph  = lipgloss.NewStyle().Bold(true).Foreground(colInfo)
)

// theme carries the width the current render is being drawn at, so panes can be
// sized from the real terminal rather than a hardcoded guess.
type theme struct {
	width int
}

// contentWidth is the usable width inside a pane's border and padding.
//
// lipgloss's Width(w) sets the TOTAL width including border and padding, so the
// inner content is w minus the chrome. Getting this wrong wraps every box, which
// is a bug that was actually shipped once in this workspace.
func (t theme) contentWidth() int {
	const chrome = 4 // two border cells, two padding cells; must track pane()'s style
	if t.width-chrome < 1 {
		return 1
	}
	return t.width - chrome
}

// pane renders body in a rounded box, focused or not.
func (t theme) pane(title string, body string, focused bool) string {
	style := stylePane
	if focused {
		style = stylePaneFocus
	}
	width := t.width
	if width < MinWidth {
		width = MinWidth
	}
	heading := styleTitle.Render(title)
	if title == "" {
		heading = ""
	} else {
		heading += "\n"
	}
	// Width(w) on a bordered, padded style is the TOTAL width, so the content is
	// w minus this style's chrome (two border cells, two padding cells). Using
	// w-2 here while contentWidth() reported w-4 made every row two cells too
	// optimistic and silently clipped the trailing value.
	return style.Width(width).Render(heading + body)
}

// deltaStyle colours a value by whether it is a gain or a loss for lap A.
//
// Positive means lap A was faster, so it is a success; negative is an error.
// Exactly zero is neutral and stays muted, because colouring it either way would
// imply a difference that is not there.
func deltaStyle(v float64) lipgloss.Style {
	switch {
	case v > 0:
		return styleSuccess
	case v < 0:
		return styleError
	default:
		return styleMuted
	}
}

// renderSectorTable draws the per-sector time delta, which is the only panel
// built from real recorded times rather than derived telemetry differences.
func (t theme) renderSectorTable(deltas []analysis.SectorDelta, lapA, lapB string) string {
	if len(deltas) == 0 {
		return styleMuted.Render("no sector times recorded for these laps")
	}
	var b strings.Builder
	b.WriteString(styleSubtitle.Render("sector   " + truncate(lapA, 10) + "   " + truncate(lapB, 10) + "     delta"))
	b.WriteString("\n")
	worst, hasWorst := analysis.WorstSector(deltas)
	for _, d := range deltas {
		if !d.Present {
			b.WriteString(styleMuted.Render(padRight("S"+itoa(d.Index), 8) + "not recorded"))
			b.WriteString("\n")
			continue
		}
		line := padRight("S"+itoa(d.Index), 8) +
			padLeft(analysis.FormatSector(d.LapAMs), 10) + "   " +
			padLeft(analysis.FormatSector(d.LapBMs), 10) + "  " +
			padLeft(analysis.FormatDelta(d.DeltaMs), 10)
		style := deltaStyle(-d.DeltaMs) // a positive sector delta is time LOST
		if hasWorst && d.Index == worst.Index && d.DeltaMs > 0 {
			line += "  worst"
		}
		b.WriteString(style.Render(line))
		b.WriteString("\n")
	}
	return strings.TrimRight(b.String(), "\n")
}

// renderTrace draws the speed delta across the lap as bars, one row per segment.
//
// This is the "shape of the lap" view: the point is to see where a loss starts
// and ends, which a single number cannot convey.
func (t theme) renderTrace(segments []analysis.Segment, top int) string {
	if len(segments) == 0 {
		return styleMuted.Render("no distance-aligned telemetry available")
	}
	_, maxAbs := analysis.SpeedRange(segments)
	if maxAbs < 0 {
		maxAbs = -maxAbs
	}
	if maxAbs == 0 {
		maxAbs = 1
	}

	// Columns: label, space, bar, space, signed value. Deriving the bar from the
	// remaining space keeps a signed value like "-14.000" from being clipped.
	const (
		labelWidth = 14
		valueWidth = 8
		separators = 2
	)
	barWidth := t.contentWidth() - labelWidth - valueWidth - separators
	if barWidth < 8 {
		barWidth = 8
	}

	shown := segments
	if top > 0 && len(shown) > top {
		shown = shown[:top]
	}

	var b strings.Builder
	b.WriteString(styleSubtitle.Render("distance      speed delta (±" + itoa(int(maxAbs)) + " km/h)"))
	b.WriteString("\n")
	for _, s := range shown {
		bar := analysis.Bar(s.MeanSpeedDelta, maxAbs, barWidth, barFill, barEmpty)
		row := padRight(itoa(int(s.StartM))+"-"+itoa(int(s.EndM))+"m", labelWidth) +
			" " + deltaStyle(s.MeanSpeedDelta).Render(bar) +
			" " + deltaStyle(s.MeanSpeedDelta).Render(padLeft(signed(s.MeanSpeedDelta), valueWidth))
		b.WriteString(row)
		b.WriteString("\n")
	}
	return strings.TrimRight(b.String(), "\n")
}

// renderTimeline draws the whole lap as a single compressed row, so the shapes a
// driver cares about stay visible even when the detailed trace is scrolled off.
func (t theme) renderTimeline(segments []analysis.Segment) string {
	if len(segments) == 0 {
		return ""
	}
	_, maxAbs := analysis.SpeedRange(segments)
	if maxAbs < 0 {
		maxAbs = -maxAbs
	}
	if maxAbs == 0 {
		maxAbs = 1
	}

	width := t.contentWidth() - 4
	if width < 8 {
		width = 8
	}
	// One cell per bucket keeps the row a fixed width; each cell is a bar of 1.
	var b strings.Builder
	step := 1
	if len(segments) > width {
		step = (len(segments) + width - 1) / width
	}
	for i := 0; i < len(segments); i += step {
		v := segments[i].MeanSpeedDelta
		// A single cell cannot show a centred bar, so use a sign glyph.
		switch {
		case v > maxAbs/3:
			b.WriteString(styleSuccess.Render("="))
		case v < -maxAbs/3:
			b.WriteString(styleError.Render("="))
		default:
			b.WriteString(styleDim.Render("-"))
		}
	}
	return b.String()
}

// renderRanked lists the segments where lap A loses the most speed.
func (t theme) renderRanked(segments []analysis.Segment, title string, top int) string {
	ranked := analysis.RankBySpeedDeficit(segments, top)
	if len(ranked) == 0 {
		return styleMuted.Render("nothing to rank")
	}
	var b strings.Builder
	b.WriteString(styleSubtitle.Render(title))
	b.WriteString("\n")
	for i, s := range ranked {
		bar := analysis.Bar(s.MeanSpeedDelta, 40, 12, barFill, barEmpty)
		b.WriteString(styleMuted.Render(itoa(i+1) + ". "))
		b.WriteString(styleText.Render(padRight(itoa(int(s.StartM))+"-"+itoa(int(s.EndM))+"m", 14)))
		b.WriteString(deltaStyle(s.MeanSpeedDelta).Render(bar + " " + padLeft(signed(s.MeanSpeedDelta), 8) + " km/h"))
		b.WriteString("\n")
	}
	return strings.TrimRight(b.String(), "\n")
}

// renderList draws a selectable list with an inverted cursor row.
func (t theme) renderList(items []string, cursor, height int) string {
	if len(items) == 0 {
		return styleMuted.Render("nothing to show")
	}
	// Window the list so a long result set cannot overflow the pane.
	start := 0
	if height > 0 && len(items) > height {
		if cursor >= height/2 {
			start = cursor - height/2
		}
		if start+height > len(items) {
			start = len(items) - height
		}
		if start < 0 {
			start = 0
		}
	}
	end := len(items)
	if height > 0 && start+height < end {
		end = start + height
	}

	var b strings.Builder
	for i := start; i < end; i++ {
		label := truncate(items[i], t.contentWidth()-2)
		if i == cursor {
			b.WriteString(styleSelected.Render(" " + padRight(label, t.contentWidth()-2)))
		} else {
			b.WriteString(styleText.Render(" " + label))
		}
		b.WriteString("\n")
	}
	return strings.TrimRight(b.String(), "\n")
}

// renderKeyHints draws the footer keymap, dropping whole bindings that do not
// fit so a narrow terminal never wraps the footer onto extra lines.
func renderKeyHints(pairs [][2]string, width int) string {
	const separator = "  ·  "
	sepWidth := lipgloss.Width(separator)

	var b strings.Builder
	used := 0
	for i, p := range pairs {
		chunk := styleKeyGlyph.Render(p[0]) + " " + styleKeyHint.Render(p[1])
		needed := lipgloss.Width(p[0]) + 1 + lipgloss.Width(p[1])
		if i > 0 {
			needed += sepWidth
		}
		if width > 0 && used+needed > width {
			break
		}
		if i > 0 {
			b.WriteString(styleDim.Render(separator))
		}
		b.WriteString(chunk)
		used += needed
	}
	return b.String()
}

// renderStatusBar draws the mode-aware footer.
func renderStatusBar(width int, mode string, detail string) string {
	label := styleSelected.Render(" " + strings.ToUpper(mode) + " ")
	// The detail is what gets dropped when space is short: the mode is the more
	// important half, and a detail that overflowed would wrap the status bar.
	remaining := width - lipgloss.Width(label) - 1
	body := ""
	if remaining >= 4 {
		body = " " + styleText.Render(truncate(detail, remaining))
	}
	line := label + body
	if pad := width - lipgloss.Width(line); pad > 0 {
		line += strings.Repeat(" ", pad)
	}
	return styleStatusBar.Width(width).Render(line)
}

// --- small text helpers -----------------------------------------------------

func itoa(v int) string {
	return strconv.Itoa(v)
}

func signed(v float64) string {
	return analysis.FormatDelta(v)
}

// truncate shortens a label to width cells so a long id cannot break a row.
func truncate(s string, width int) string {
	if width <= 0 {
		return ""
	}
	runes := []rune(s)
	if len(runes) <= width {
		return s
	}
	if width <= 1 {
		return string(runes[:width])
	}
	return string(runes[:width-1]) + "…"
}

// padRight pads to width cells, truncating if the label is longer.
func padRight(s string, width int) string {
	if width <= 0 {
		return ""
	}
	trimmed := truncate(s, width)
	if pad := width - lipgloss.Width(trimmed); pad > 0 {
		return trimmed + strings.Repeat(" ", pad)
	}
	return trimmed
}

// padLeft right-aligns within width cells.
func padLeft(s string, width int) string {
	if width <= 0 {
		return ""
	}
	trimmed := truncate(s, width)
	if pad := width - lipgloss.Width(trimmed); pad > 0 {
		return strings.Repeat(" ", pad) + trimmed
	}
	return trimmed
}
