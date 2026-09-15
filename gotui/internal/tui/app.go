// Package tui is the f1-telemetry-oracle terminal UI: a race-engineer console
// built on charm.land/bubbletea/v2, with huh/v2 forms for the interactive
// choices and a plain renderer for non-TTY use.
//
// It is a read-only peer of the Next.js dashboard. Every number it shows comes
// from the project's own FastAPI service (api/), so a terminal user and a
// browser user see identical results: this front-end holds no lap, comparison,
// telemetry or strategy logic of its own. Where it draws a derived view -- the
// sector delta sign, the distance-segment ranking -- the derivation is stated in
// internal/analysis and never claims more than the payload supports.
package tui

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/analysis"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/session"
)

// screen identifies the active view.
type screen int

const (
	screenMenu screen = iota
	screenCircuits
	screenSessions
	screenLaps
	screenCompare
	screenSimVsReal
	screenTwin
	screenStrategy
	screenChat
)

// screenTitle is the human label used in the header.
func screenTitle(s screen) string {
	switch s {
	case screenCircuits:
		return "Circuits"
	case screenSessions:
		return "Sessions"
	case screenLaps:
		return "Laps"
	case screenCompare:
		return "Lap comparison"
	case screenSimVsReal:
		return "Sim vs real"
	case screenTwin:
		return "Driving twin"
	case screenStrategy:
		return "Strategy simulation"
	case screenChat:
		return "Race engineer"
	default:
		return "Menu"
	}
}

// Options configures the model.
type Options struct {
	Client     *api.Client
	Settings   session.Settings
	Plain      bool
	Accessible bool
	NoColor    bool
	ListHeight int
}

// Model is the root bubbletea model.
//
// It is a pointer model on purpose: every huh field binds through a pointer, and
// a value-typed Bubble Tea model would silently persist form defaults because
// Update receives a copy.
type Model struct {
	width  int
	height int
	opts   Options

	client *api.Client

	screen     screen
	menuCursor int

	circuits []api.Circuit
	sessions []api.Session
	laps     []api.Lap

	comparison *api.LapComparison
	simVsReal  *api.SimVsReal
	twin       *api.DrivingTwin
	strategy   *api.StrategySim
	chat       *api.ChatResponse

	// Comparison inputs, kept so the results pane can label the two laps.
	lapAID string
	lapBID string

	// Session/lap filters, seeded from the forms.
	sessionSource string
	lapSessionID  string
	lapDriverID   string
	twinLapID     string
	simLapID      string

	strategyAnswers StrategyAnswers
	askText         string

	// answers holds the bound values of the currently open form. A single struct
	// is reused because every huh field binds through a pointer.
	answers Answers

	form        *huh.Form
	formPurpose formPurpose

	listCursor int

	// busy is a static label rather than a spinner. A spinner needs a timer
	// command, and a timer command is exactly what makes a test suite hang: the
	// command blocks on its channel and every re-arm reschedules it. Refreshes
	// here are user-driven, so there is nothing to animate.
	busy    string
	failure string
	notice  string

	viewport viewport.Model

	// plain disables the full-screen renderer for this model. It is set when the
	// caller asked for --plain, and never because the TUI looked fine.
	plain bool
}

// New builds the root model.
func New(opts Options) *Model {
	m := &Model{
		opts:   opts,
		client: opts.Client,
		screen: screenMenu,
		plain:  opts.Plain,
	}
	height := opts.ListHeight
	if height <= 0 {
		height = 14
	}
	m.viewport = viewport.New()
	m.viewport.SetHeight(height)
	m.strategyAnswers = defaultStrategyAnswers()
	return m
}

// Init implements tea.Model. It performs no initial request: the menu is the
// first screen and opening it must not depend on the service being up, so that a
// user with a stopped database still gets a readable UI and the guidance for it.
func (m *Model) Init() tea.Cmd { return nil }

// --- messages ---------------------------------------------------------------

type circuitsLoadedMsg struct {
	circuits []api.Circuit
	err      error
}

type sessionsLoadedMsg struct {
	sessions []api.Session
	err      error
}

type lapsLoadedMsg struct {
	laps []api.Lap
	err  error
}

type comparisonLoadedMsg struct {
	comparison *api.LapComparison
	err        error
}

type simVsRealLoadedMsg struct {
	result *api.SimVsReal
	err    error
}

type twinLoadedMsg struct {
	twin *api.DrivingTwin
	err  error
}

type strategyLoadedMsg struct {
	strategy *api.StrategySim
	err      error
}

type chatLoadedMsg struct {
	chat *api.ChatResponse
	err  error
}

// --- commands ---------------------------------------------------------------

func (m *Model) loadCircuitsCmd() tea.Cmd {
	client := m.client
	return func() tea.Msg {
		circuits, err := client.Circuits(context.Background(), 100)
		return circuitsLoadedMsg{circuits: circuits, err: err}
	}
}

func (m *Model) loadSessionsCmd() tea.Cmd {
	client, source := m.client, m.sessionSource
	return func() tea.Msg {
		sessions, err := client.Sessions(context.Background(), source, 100)
		return sessionsLoadedMsg{sessions: sessions, err: err}
	}
}

func (m *Model) loadLapsCmd() tea.Cmd {
	client, sessionID, driverID := m.client, m.lapSessionID, m.lapDriverID
	return func() tea.Msg {
		laps, err := client.Laps(context.Background(), sessionID, driverID, 100)
		return lapsLoadedMsg{laps: laps, err: err}
	}
}

func (m *Model) compareCmd() tea.Cmd {
	client, a, b := m.client, m.lapAID, m.lapBID
	return func() tea.Msg {
		comparison, err := client.CompareLaps(context.Background(), []string{a, b})
		return comparisonLoadedMsg{comparison: comparison, err: err}
	}
}

func (m *Model) simVsRealCmd() tea.Cmd {
	client, lapID := m.client, m.simLapID
	return func() tea.Msg {
		result, err := client.SimVsReal(context.Background(), lapID)
		return simVsRealLoadedMsg{result: result, err: err}
	}
}

func (m *Model) twinCmd() tea.Cmd {
	client, lapID := m.client, m.twinLapID
	return func() tea.Msg {
		twin, err := client.DrivingTwin(context.Background(), lapID, 5)
		return twinLoadedMsg{twin: twin, err: err}
	}
}

func (m *Model) strategyCmd() tea.Cmd {
	client := m.client
	req := m.strategyAnswers.Request()
	return func() tea.Msg {
		strategy, err := client.StrategySim(context.Background(), req)
		return strategyLoadedMsg{strategy: strategy, err: err}
	}
}

func (m *Model) chatCmd() tea.Cmd {
	client, question := m.client, m.askText
	return func() tea.Msg {
		chat, err := client.Chat(context.Background(), api.ChatRequest{
			Message:          question,
			IncludeTelemetry: true,
		})
		return chatLoadedMsg{chat: chat, err: err}
	}
}

// --- update -----------------------------------------------------------------

// Update implements tea.Model.
func (m *Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.resize()
		return m, nil

	case tea.KeyPressMsg:
		return m.handleKey(msg)

	case circuitsLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.circuits = msg.circuits
		m.listCursor = 0
		if len(msg.circuits) == 0 {
			m.notice = "no circuits returned; seed the database (scripts/seed_circuits.py)"
		}
		return m, nil

	case sessionsLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.sessions = msg.sessions
		m.listCursor = 0
		if len(msg.sessions) == 0 {
			m.notice = "no sessions matched that filter"
		}
		return m, nil

	case lapsLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.laps = msg.laps
		m.listCursor = 0
		if len(msg.laps) == 0 {
			m.notice = "no laps matched that filter"
		}
		return m, nil

	case comparisonLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.comparison = msg.comparison
		m.screen = screenCompare
		if len(msg.comparison.Deltas) == 0 {
			m.notice = "the service returned no distance-aligned telemetry for these laps"
		}
		return m, nil

	case simVsRealLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.simVsReal = msg.result
		m.screen = screenSimVsReal
		return m, nil

	case twinLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.twin = msg.twin
		m.screen = screenTwin
		return m, nil

	case strategyLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.strategy = msg.strategy
		m.screen = screenStrategy
		return m, nil

	case chatLoadedMsg:
		m.busy = ""
		m.failure = ""
		if msg.err != nil {
			m.failure = describe(msg.err)
			return m, nil
		}
		m.chat = msg.chat
		return m, nil
	}

	// An embedded huh form has to see every other message.
	if m.form != nil {
		return m.updateForm(msg)
	}
	return m, nil
}

// handleKey routes a key press. Only KeyPressMsg is handled: bubbletea v2 also
// delivers key RELEASES, and acting on both makes every binding fire twice,
// which is a bug that was actually shipped once in this workspace.
func (m *Model) handleKey(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	if m.form != nil {
		// ctrl+c must always be able to leave, even mid-form.
		if msg.String() == "ctrl+c" {
			return m, tea.Quit
		}
		// huh's default form keymap binds Quit to ctrl+c only, so escape would
		// otherwise do nothing and the footer's "esc cancel" would be a lie. The
		// user would be stuck in the form with no advertised way out.
		if msg.String() == "esc" {
			m.form = nil
			m.formPurpose = purposeNone
			m.notice = "Cancelled."
			return m, nil
		}
		// The form owns everything else, including "q" and the arrow keys.
		return m.updateForm(msg)
	}

	switch msg.String() {
	case "ctrl+c":
		return m, tea.Quit
	case "esc":
		if m.screen != screenMenu {
			m.screen = screenMenu
			m.failure = ""
			m.notice = ""
			return m, nil
		}
		return m, tea.Quit
	case "q":
		if m.screen == screenMenu {
			return m, tea.Quit
		}
		m.screen = screenMenu
		return m, nil
	}

	if m.screen == screenMenu {
		return m.updateMenu(msg)
	}
	switch m.screen {
	case screenCircuits, screenSessions, screenLaps:
		return m.updateList(msg)
	case screenCompare, screenTwin:
		return m.updateScroll(msg)
	}
	return m, nil
}

// updateMenu drives the main menu.
func (m *Model) updateMenu(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	items := menuItems()
	switch msg.String() {
	case "up", "k":
		if m.menuCursor > 0 {
			m.menuCursor--
		}
	case "down", "j":
		if m.menuCursor < len(items)-1 {
			m.menuCursor++
		}
	case "enter", " ":
		return m.activateMenuItem(items[m.menuCursor].ID)
	}
	return m, nil
}

// activateMenuItem opens a screen or opens the form that feeds it.
func (m *Model) activateMenuItem(id string) (tea.Model, tea.Cmd) {
	m.failure = ""
	m.notice = ""
	switch id {
	case menuCircuits:
		m.screen = screenCircuits
		m.busy = "Loading circuits"
		return m, m.loadCircuitsCmd()
	case menuSessions:
		m.screen = screenSessions
		m.busy = "Loading sessions"
		return m, m.loadSessionsCmd()
	case menuLaps:
		m.screen = screenLaps
		m.busy = "Loading laps"
		return m, m.loadLapsCmd()
	case menuCompare:
		return m.openForm(purposeCompare, CompareForm(&m.answers, m.lapAID, m.lapBID))
	case menuSimVsReal:
		return m.openForm(purposeSimVsReal, LapIDForm(&m.answers, "Sim lap to compare"))
	case menuTwin:
		return m.openForm(purposeTwin, LapIDForm(&m.answers, "Sim lap to analyse"))
	case menuStrategy:
		return m.openForm(purposeStrategy, StrategyForm(&m.answers, &m.strategyAnswers))
	case menuChat:
		return m.openForm(purposeChat, AskForm(&m.answers))
	}
	return m, nil
}

// updateList drives a scrollable selection list.
func (m *Model) updateList(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	items := m.currentListItems()
	if len(items) == 0 {
		if msg.String() == "r" {
			return m.reloadCurrent()
		}
		return m, nil
	}
	switch msg.String() {
	case "up", "k":
		if m.listCursor > 0 {
			m.listCursor--
		}
	case "down", "j":
		if m.listCursor < len(items)-1 {
			m.listCursor++
		}
	case "pgup":
		m.listCursor -= m.listPage()
		if m.listCursor < 0 {
			m.listCursor = 0
		}
	case "pgdown":
		m.listCursor += m.listPage()
		if m.listCursor > len(items)-1 {
			m.listCursor = len(items) - 1
		}
	case "g":
		m.listCursor = 0
	case "G":
		m.listCursor = len(items) - 1
	case "r":
		return m.reloadCurrent()
	case "c":
		// Compare the highlighted lap against one already chosen, or start a pair.
		if m.screen == screenLaps && len(m.laps) > 0 {
			id := m.laps[m.listCursor].LapID
			switch {
			case m.lapAID == "":
				m.lapAID = id
				m.notice = "first lap selected: " + id + " — pick another and press c"
			case m.lapBID == "" && id != m.lapAID:
				m.lapBID = id
				m.busy = "Comparing"
				return m, m.compareCmd()
			default:
				m.lapAID, m.lapBID = id, ""
				m.notice = "restarted the pair with " + id
			}
		}
	case "enter":
		return m.openFromListCursor()
	}
	return m, nil
}

// openFromListCursor turns the highlighted row into the next action.
func (m *Model) openFromListCursor() (tea.Model, tea.Cmd) {
	switch m.screen {
	case screenSessions:
		if m.listCursor < len(m.sessions) {
			m.lapSessionID = m.sessions[m.listCursor].SessionID
			m.screen = screenLaps
			m.busy = "Loading laps"
			return m, m.loadLapsCmd()
		}
	case screenLaps:
		if m.listCursor < len(m.laps) {
			m.twinLapID = m.laps[m.listCursor].LapID
			m.busy = "Analysing driving style"
			return m, m.twinCmd()
		}
	}
	return m, nil
}

// reloadCurrent repeats the request that fills the active list.
func (m *Model) reloadCurrent() (tea.Model, tea.Cmd) {
	m.notice = ""
	switch m.screen {
	case screenCircuits:
		m.busy = "Loading circuits"
		return m, m.loadCircuitsCmd()
	case screenSessions:
		m.busy = "Loading sessions"
		return m, m.loadSessionsCmd()
	case screenLaps:
		m.busy = "Loading laps"
		return m, m.loadLapsCmd()
	}
	return m, nil
}

// updateScroll drives the viewport on the long result screens.
func (m *Model) updateScroll(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "up", "k":
		m.viewport.ScrollUp(1)
	case "down", "j":
		m.viewport.ScrollDown(1)
	case "pgup":
		m.viewport.PageUp()
	case "pgdown":
		m.viewport.PageDown()
	case "g":
		m.viewport.GotoTop()
	case "G":
		m.viewport.GotoBottom()
	}
	return m, nil
}

// updateForm drives the active form.
func (m *Model) updateForm(msg tea.Msg) (tea.Model, tea.Cmd) {
	updated, cmd := m.form.Update(msg)
	if form, ok := updated.(*huh.Form); ok {
		m.form = form
	}
	if m.form.State != huh.StateNormal {
		return m, m.advance()
	}
	return m, cmd
}

// openForm installs a form sized to the terminal and returns its first command.
//
// Every transition goes through here so no form is ever left at huh's default
// zero width, which renders as blank lines.
func (m *Model) openForm(purpose formPurpose, form *huh.Form) (tea.Model, tea.Cmd) {
	m.form = m.sized(form)
	m.formPurpose = purpose
	m.notice = ""
	return m, m.form.Init()
}

// sized pins a form to the model's dimensions.
func (m *Model) sized(f *huh.Form) *huh.Form {
	width := m.width - 4
	if width < MinWidth {
		width = MinWidth
	}
	return f.WithWidth(width).WithHeight(m.height)
}

// advance reacts to a finished form.
//
// The form's answer is only readable once it has actually completed: pressing
// enter returns a command that moves the form along, it does not finish it in the
// same call. Every branch here therefore runs after that command has been
// processed by Update, never before.
func (m *Model) advance() tea.Cmd {
	state := m.form.State
	purpose := m.formPurpose
	m.form = nil
	m.formPurpose = purposeNone

	if state == huh.StateAborted {
		m.notice = "Cancelled."
		return nil
	}

	switch purpose {
	case purposeCompare:
		m.lapAID = strings.TrimSpace(m.answers.LapA)
		m.lapBID = strings.TrimSpace(m.answers.LapB)
		if m.lapAID == m.lapBID {
			m.failure = "pick two different laps: both fields hold " + m.lapAID
			return nil
		}
		m.busy = "Comparing"
		return m.compareCmd()
	case purposeSimVsReal:
		m.simLapID = strings.TrimSpace(m.answers.LapID)
		m.busy = "Matching a real lap"
		return m.simVsRealCmd()
	case purposeTwin:
		m.twinLapID = strings.TrimSpace(m.answers.LapID)
		m.busy = "Analysing driving style"
		return m.twinCmd()
	case purposeStrategy:
		m.busy = "Simulating strategies"
		return m.strategyCmd()
	case purposeChat:
		m.askText = strings.TrimSpace(m.answers.Question)
		if m.askText == "" {
			m.failure = "ask something first"
			return nil
		}
		m.screen = screenChat
		m.busy = "Asking the race engineer"
		return m.chatCmd()
	}
	return nil
}

// resize keeps the viewport in step with the terminal.
func (m *Model) resize() {
	m.viewport.SetWidth(m.bodyWidth())
	height := m.height - 8
	if height < 3 {
		height = 3
	}
	m.viewport.SetHeight(height)
}

// listPage is how many rows a page key moves.
func (m *Model) listPage() int {
	page := m.listHeight() - 1
	if page < 1 {
		page = 1
	}
	return page
}

func (m *Model) listHeight() int {
	height := m.height - 9
	if height < 3 {
		height = 3
	}
	return height
}

func (m *Model) bodyWidth() int {
	width := m.width - 6
	if width < MinWidth {
		width = MinWidth
	}
	return width
}

// --- view -------------------------------------------------------------------

// View implements tea.Model.
func (m *Model) View() tea.View {
	view := tea.NewView(m.Render())
	view.AltScreen = true
	return view
}

// Render draws the whole UI as a string. It is exported so a test can assert on
// frames without a terminal, and so the plain renderer can share it.
func (m *Model) Render() string {
	width := m.width
	if width < MinWidth {
		width = MinWidth
	}

	var b strings.Builder
	b.WriteString(m.renderHeader(width))
	b.WriteString("\n\n")

	b.WriteString(m.body())
	b.WriteString("\n")

	if m.failure != "" {
		b.WriteString(styleError.Render(wrapPlain(m.failure, width)))
		b.WriteString("\n")
	}
	if m.notice != "" {
		b.WriteString(styleWarning.Render(wrapPlain(m.notice, width)))
		b.WriteString("\n")
	}

	b.WriteString(renderKeyHints(m.keyHints(), width))
	b.WriteString("\n")
	b.WriteString(renderStatusBar(width, m.modeLabel(), m.statusDetail()))

	// Final guarantee: no rendered line may exceed the terminal. Individual
	// renderers truncate their own free text so cuts land at sensible points, but
	// this clamps the whole frame so adding a new line can never reintroduce a
	// wrap. MaxWidth is ANSI-aware, so it will not cut an escape sequence in half.
	return lipgloss.NewStyle().MaxWidth(width).Render(b.String())
}

// headerSegment is one piece of the title bar.
//
// Segments are measured and dropped from the right as the terminal narrows, so
// a long URL can never force the header wider than the screen and wrap every row
// below it. Truncating the assembled ANSI string instead would risk cutting an
// escape sequence in half.
type headerSegment struct {
	text  string
	style lipgloss.Style
}

// renderHeader composes the title bar within width cells.
func (m *Model) renderHeader(width int) string {
	if width < 1 {
		return ""
	}
	segments := []headerSegment{
		{text: "F1 Telemetry Oracle", style: styleTitle},
		{text: screenTitle(m.screen), style: styleSubtitle},
	}
	if m.client != nil {
		segments = append(segments, headerSegment{text: m.client.BaseURL(), style: styleMuted})
	}
	if m.lapAID != "" {
		label := m.lapAID
		if m.lapBID != "" {
			label += " vs " + m.lapBID
		} else {
			label += " (press c for a second)"
		}
		segments = append(segments, headerSegment{text: label, style: styleInfo})
	}

	const separator = "  ·  "
	sepWidth := lipgloss.Width(separator)

	var b strings.Builder
	used := 0
	for i, segment := range segments {
		textWidth := lipgloss.Width(segment.text)
		needed := textWidth
		if i > 0 {
			needed += sepWidth
		}
		if used+needed > width {
			// Drop the rest; optionally show a shortened final segment so the
			// screen name still appears on a very narrow terminal.
			remaining := width - used - sepWidth
			if i > 0 && remaining > 4 {
				b.WriteString(styleDim.Render(separator))
				b.WriteString(segment.style.Render(truncate(segment.text, remaining)))
			}
			break
		}
		if i > 0 {
			b.WriteString(styleDim.Render(separator))
		}
		b.WriteString(segment.style.Render(segment.text))
		used += needed
	}
	return b.String()
}

// body draws the active screen.
func (m *Model) body() string {
	t := theme{width: m.bodyWidth()}

	if m.form != nil {
		return m.form.View() + "\n"
	}
	switch m.screen {
	case screenCircuits:
		return t.pane("Circuits", m.renderCircuits(), true) + "\n"
	case screenSessions:
		return t.pane("Sessions", m.renderSessions(), true) + "\n"
	case screenLaps:
		return t.pane("Laps", m.renderLaps(), true) + "\n"
	case screenCompare:
		return m.renderCompare()
	case screenSimVsReal:
		return m.renderSimVsReal()
	case screenTwin:
		return m.renderTwin()
	case screenStrategy:
		return m.renderStrategy()
	case screenChat:
		return m.renderChat()
	}
	return t.pane("Race engineer console", m.renderMenu(), true) + "\n"
}

func (m *Model) renderMenu() string {
	var b strings.Builder
	b.WriteString(styleSubtitle.Render("Compare sim telemetry against real F1 data."))
	b.WriteString("\n\n")
	for i, item := range menuItems() {
		label := item.Label
		if i == m.menuCursor {
			b.WriteString(styleSelected.Render(" " + padRight(label, m.bodyWidth()-6) + " "))
		} else {
			b.WriteString(styleText.Render("   " + label))
		}
		b.WriteString("\n")
		if item.Hint != "" {
			b.WriteString(styleMuted.Render("      " + item.Hint))
			b.WriteString("\n")
		}
	}
	return strings.TrimRight(b.String(), "\n")
}

func (m *Model) renderCircuits() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	items := make([]string, 0, len(m.circuits))
	for _, c := range m.circuits {
		length := "--"
		if c.TrackLengthM != nil {
			length = fmt.Sprintf("%.0f m", *c.TrackLengthM)
		}
		items = append(items, padRight(c.CircuitID, 22)+padRight(c.DisplayName(), 34)+
			padRight(c.Country, 16)+length)
	}
	if len(items) == 0 {
		return styleMuted.Render("no circuits returned")
	}
	header := styleSubtitle.Render(padRight("id", 22) + padRight("name", 34) + padRight("country", 16) + "length")
	return header + "\n" + theme{width: m.bodyWidth()}.renderList(items, m.listCursor, m.listHeight())
}

func (m *Model) renderSessions() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	items := make([]string, 0, len(m.sessions))
	for _, s := range m.sessions {
		season := "--"
		if s.Season != nil {
			season = itoa(*s.Season)
		}
		items = append(items, padRight(s.SessionID, 26)+padRight(s.SessionType, 12)+
			padRight(s.Source, 10)+padRight(s.CircuitID, 18)+season)
	}
	if len(items) == 0 {
		return styleMuted.Render("no sessions returned")
	}
	header := styleSubtitle.Render(padRight("session", 26) + padRight("type", 12) +
		padRight("source", 10) + padRight("circuit", 18) + "season")
	hint := styleMuted.Render("enter: show this session's laps")
	return header + "\n" + hint + "\n" + theme{width: m.bodyWidth()}.renderList(items, m.listCursor, m.listHeight()-1)
}

func (m *Model) renderLaps() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	items := make([]string, 0, len(m.laps))
	for _, l := range m.laps {
		compound := "--"
		if l.TireCompound != nil {
			compound = *l.TireCompound
		}
		valid := "invalid"
		if l.IsValid {
			valid = "valid"
		}
		items = append(items, padRight(l.LapID, 26)+padRight(l.DriverID, 16)+
			padLeft(itoa(l.LapNumber), 4)+"  "+padLeft(analysis.FormatLapTime(l.LapTimeMs), 10)+
			"  "+padRight(compound, 8)+valid)
	}
	if len(items) == 0 {
		return styleMuted.Render("no laps returned")
	}
	header := styleSubtitle.Render(padRight("lap", 26) + padRight("driver", 16) +
		padLeft("no.", 4) + "  " + padLeft("lap time", 10) + "  " + padRight("tyre", 8) + "status")
	hints := styleMuted.Render("c: choose/compare a lap   enter: driving twin for this lap")
	return header + "\n" + hints + "\n" + theme{width: m.bodyWidth()}.renderList(items, m.listCursor, m.listHeight()-1)
}

// renderCompare is the centrepiece: real sector times, then the derived
// distance-segment analysis, clearly labelled as the different kind of evidence
// it is.
func (m *Model) renderCompare() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	if m.comparison == nil {
		return styleMuted.Render("no comparison loaded")
	}
	t := theme{width: m.bodyWidth()}

	lapA, lapB := m.lapAID, m.lapBID
	if len(m.comparison.LapIDs) >= 2 {
		lapA, lapB = m.comparison.LapIDs[0], m.comparison.LapIDs[1]
	}

	var b strings.Builder
	sectors := analysis.SectorDeltas(m.comparison.SectorDeltas)
	b.WriteString(t.pane("Sector times (recorded — this is real time)", t.renderSectorTable(sectors, lapA, lapB), true))
	b.WriteString("\n")

	if worst, ok := analysis.WorstSector(sectors); ok && worst.DeltaMs > 0 {
		b.WriteString(styleWarning.Render(truncate(
			fmt.Sprintf("Biggest time loss: sector %d, %s", worst.Index, analysis.FormatDelta(worst.DeltaMs)+" ms"),
			m.bodyWidth())))
		b.WriteString("\n")
	}

	segments := analysis.Segments(m.comparison.Deltas, 100)
	b.WriteString("\n")
	b.WriteString(styleSubtitle.Render("Whole lap, fastest above the line"))
	b.WriteString("\n")
	b.WriteString(t.renderTimeline(segments))
	b.WriteString("\n\n")

	b.WriteString(t.pane("Speed delta by distance (derived — not an elapsed time)",
		t.renderTrace(segments, 10), false))
	b.WriteString("\n")
	b.WriteString(t.pane("Where you lose the most speed",
		t.renderRanked(segments, "ranked by worst speed deficit in each 100 m", 6), false))
	b.WriteString("\n")
	if braking := analysis.BrakingSegments(segments, 5); len(braking) > 0 {
		b.WriteString(t.pane("Braking losses", t.renderRanked(braking, "where you brake later/harder than the reference", 5), false))
		b.WriteString("\n")
	}
	return b.String()
}

func (m *Model) renderSimVsReal() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	if m.simVsReal == nil {
		return styleMuted.Render("no comparison loaded")
	}
	t := theme{width: m.bodyWidth()}
	var b strings.Builder
	b.WriteString(styleSubtitle.Render("sim lap  " + truncate(m.simVsReal.SimLapID, m.bodyWidth()-10)))
	b.WriteString("\n")
	b.WriteString(styleSubtitle.Render("real lap " + truncate(m.simVsReal.RealLapID, m.bodyWidth()-10)))
	b.WriteString("\n")
	b.WriteString(styleMuted.Render("circuit  " + truncate(m.simVsReal.CircuitID, m.bodyWidth()-10)))
	b.WriteString("\n\n")

	sectors := analysis.SectorDeltas(m.simVsReal.Comparison.SectorDeltas)
	b.WriteString(t.pane("Sector times", t.renderSectorTable(sectors, m.simVsReal.SimLapID, m.simVsReal.RealLapID), true))
	b.WriteString("\n")
	segments := analysis.Segments(m.simVsReal.Comparison.Deltas, 100)
	b.WriteString(t.pane("Speed delta by distance (derived)",
		t.renderTrace(segments, 12), false))
	b.WriteString("\n")
	return b.String()
}

func (m *Model) renderTwin() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	if m.twin == nil {
		return styleMuted.Render("no analysis loaded")
	}
	if m.twin.Error != "" {
		return styleWarning.Render(truncate("the service reported: "+m.twin.Error, m.bodyWidth()))
	}
	var b strings.Builder
	if m.twin.OverallTwin != nil {
		b.WriteString(styleTitle.Render(truncate("You drive like "+m.twin.OverallTwin.DriverCode, m.bodyWidth())))
		b.WriteString("\n")
		b.WriteString(styleMuted.Render(truncate(fmt.Sprintf(
			"mean cosine distance %.4f (lower is closer)", m.twin.OverallTwin.MeanSimilarity), m.bodyWidth())))
		b.WriteString("\n\n")
	}
	t := theme{width: m.bodyWidth()}
	for _, sector := range m.twin.Sectors {
		var rows strings.Builder
		if len(sector.Matches) == 0 {
			rows.WriteString(styleMuted.Render("no comparable real laps in this sector"))
		}
		for _, match := range sector.Matches {
			rows.WriteString(styleText.Render(padRight(match.Driver, 22)))
			rows.WriteString(styleMuted.Render(padRight(" "+match.Code, 8)))
			rows.WriteString(styleInfo.Render("distance " + fmt.Sprintf("%.4f", match.Similarity)))
			rows.WriteString("\n")
		}
		b.WriteString(t.pane("Sector "+itoa(sector.Sector), strings.TrimRight(rows.String(), "\n"), false))
		b.WriteString("\n")
	}
	return b.String()
}

func (m *Model) renderStrategy() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	if m.strategy == nil {
		return styleMuted.Render("no simulation loaded")
	}
	t := theme{width: m.bodyWidth()}
	var b strings.Builder
	b.WriteString(styleMuted.Render(truncate(fmt.Sprintf("%d laps · %d sims · track %.0f C",
		m.strategy.TotalLaps, m.strategy.NSims, m.strategy.TrackTempC), m.bodyWidth())))
	b.WriteString("\n\n")

	var rows strings.Builder
	rows.WriteString(styleSubtitle.Render(
		padLeft("rank", 5) + "  " + padRight("strategy", 26) + padLeft("median", 10) +
			padLeft("p10", 10) + padLeft("p90", 10) + "  win probability"))
	rows.WriteString("\n")
	for _, s := range m.strategy.Strategies {
		win := analysis.ProgressBar(s.WinProbability, 12, barFill, barEmpty)
		rows.WriteString(styleMuted.Render(padLeft(itoa(s.Rank), 5) + "  "))
		rows.WriteString(styleText.Render(padRight(strings.Join(s.Strategy, " → "), 26)))
		rows.WriteString(styleText.Render(padLeft(analysis.FormatMillis(s.MedianRaceTimeS*1000), 10)))
		rows.WriteString(styleMuted.Render(padLeft(analysis.FormatMillis(s.P10RaceTimeS*1000), 10)))
		rows.WriteString(styleMuted.Render(padLeft(analysis.FormatMillis(s.P90RaceTimeS*1000), 10)))
		rows.WriteString("  ")
		rows.WriteString(styleSuccess.Render(win))
		rows.WriteString(styleInfo.Render(fmt.Sprintf(" %.0f%%", s.WinProbability*100)))
		rows.WriteString("\n")
	}
	b.WriteString(t.pane("Ranked pit strategies (Monte Carlo)", strings.TrimRight(rows.String(), "\n"), true))
	b.WriteString("\n")
	b.WriteString(styleMuted.Render(truncate(
		"win probability is this strategy's share of simulated wins, not a prediction of the real race",
		m.bodyWidth())))
	b.WriteString("\n")
	return b.String()
}

func (m *Model) renderChat() string {
	if m.busy != "" {
		return styleMuted.Render(m.busy + "…")
	}
	if m.chat == nil {
		return styleMuted.Render("no answer yet — press enter on the menu's Ask option")
	}
	t := theme{width: m.bodyWidth()}
	var b strings.Builder
	b.WriteString(t.pane("Race engineer", m.chat.Response, true))
	b.WriteString("\n")
	var trace strings.Builder
	trace.WriteString(styleMuted.Render("path " + m.chat.Trace.Path))
	if m.chat.Intent != "" {
		trace.WriteString(styleMuted.Render("  ·  intent " + m.chat.Intent))
	}
	trace.WriteString(styleMuted.Render(fmt.Sprintf("  ·  %d ms", m.chat.ElapsedMs)))
	trace.WriteString("\n")
	if len(m.chat.Trace.ToolCalls) > 0 {
		trace.WriteString(styleInfo.Render("tools " + strings.Join(m.chat.Trace.ToolCalls, ", ")))
		trace.WriteString("\n")
	}
	for source, count := range m.chat.Sources {
		trace.WriteString(styleText.Render(fmt.Sprintf("  %s: %d", source, count)))
		trace.WriteString("\n")
	}
	b.WriteString(t.pane("Retrieval trace", strings.TrimRight(trace.String(), "\n"), false))
	b.WriteString("\n")
	return b.String()
}

// keyHints returns the footer bindings for the active screen.
func (m *Model) keyHints() [][2]string {
	if m.form != nil {
		return [][2]string{{"enter", "next"}, {"esc", "cancel"}}
	}
	switch m.screen {
	case screenMenu:
		return [][2]string{{"↑/↓", "move"}, {"enter", "open"}, {"q", "quit"}}
	case screenCircuits, screenSessions:
		return [][2]string{{"↑/↓", "move"}, {"enter", "laps"}, {"r", "reload"}, {"esc", "menu"}, {"q", "quit"}}
	case screenLaps:
		return [][2]string{{"↑/↓", "move"}, {"c", "compare"}, {"enter", "twin"}, {"r", "reload"}, {"esc", "menu"}}
	case screenCompare, screenTwin:
		return [][2]string{{"↑/↓", "scroll"}, {"g/G", "top/bottom"}, {"esc", "menu"}, {"q", "quit"}}
	default:
		return [][2]string{{"esc", "menu"}, {"q", "quit"}}
	}
}

// modeLabel names the mode segment of the status bar.
func (m *Model) modeLabel() string {
	if m.failure != "" {
		return "error"
	}
	if m.busy != "" {
		return "working"
	}
	return "ready"
}

// statusDetail is the free text in the status bar.
func (m *Model) statusDetail() string {
	if m.busy != "" {
		return m.busy
	}
	if m.failure != "" {
		return "see the message above"
	}
	switch m.screen {
	case screenCircuits:
		return fmt.Sprintf("%d circuits", len(m.circuits))
	case screenSessions:
		return fmt.Sprintf("%d sessions", len(m.sessions))
	case screenLaps:
		return fmt.Sprintf("%d laps", len(m.laps))
	}
	return "no lap selected"
}

// describe turns an error into an actionable sentence, keeping the two failure
// classes apart: a down service needs "start it", a database error needs the
// service's own text.
func describe(err error) string {
	switch {
	case err == nil:
		return ""
	case errors.Is(err, api.ErrUnreachable):
		return session.StartHint("the configured API URL")
	case errors.Is(err, api.ErrOracleDown):
		return "The API is running but its Oracle call failed. Check the database container:\n    docker compose up -d oracle\n" + err.Error()
	default:
		return err.Error()
	}
}

// wrapPlain hard-wraps text to width so a long error message cannot force the
// terminal to scroll sideways.
func wrapPlain(text string, width int) string {
	if width < 20 {
		return text
	}
	var out []string
	for _, line := range strings.Split(text, "\n") {
		if len([]rune(line)) <= width {
			out = append(out, line)
			continue
		}
		words := strings.Fields(line)
		current := ""
		for _, w := range words {
			if current == "" {
				current = w
				continue
			}
			if len([]rune(current))+1+len([]rune(w)) > width {
				out = append(out, current)
				current = w
				continue
			}
			current += " " + w
		}
		if current != "" {
			out = append(out, current)
		}
	}
	return strings.Join(out, "\n")
}

// currentListItems returns the rows of the active list screen, used by the
// cursor logic and by the plain renderer.
func (m *Model) currentListItems() []string {
	switch m.screen {
	case screenCircuits:
		items := make([]string, 0, len(m.circuits))
		for _, c := range m.circuits {
			items = append(items, c.CircuitID)
		}
		return items
	case screenSessions:
		items := make([]string, 0, len(m.sessions))
		for _, s := range m.sessions {
			items = append(items, s.SessionID)
		}
		return items
	case screenLaps:
		items := make([]string, 0, len(m.laps))
		for _, l := range m.laps {
			items = append(items, l.LapID)
		}
		return items
	}
	return nil
}
