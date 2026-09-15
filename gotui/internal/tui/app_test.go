package tui

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"charm.land/bubbles/v2/cursor"
	tea "charm.land/bubbletea/v2"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/session"
)

// --- test harness -----------------------------------------------------------

// drainTimeout bounds how long drain waits for one command to produce a message.
//
// It is needed at all because huh's fields embed a text cursor whose blink is a
// tea.Tick: calling that command synchronously blocks for the blink interval
// (about 530 ms) and, because it re-arms, a naive drain can walk it repeatedly.
// A command that has not answered within this window is treated as timer-driven
// and skipped. There are no timers in this model's own logic -- Init returns nil
// and nothing re-arms a tick -- so this only ever fires for the cursor.
const drainTimeout = 250 * time.Millisecond

func runCmd(cmd tea.Cmd) tea.Msg {
	done := make(chan tea.Msg, 1) // buffered: a late send must not leak the goroutine
	go func() {
		defer func() {
			// A command can panic when invoked outside the Bubble Tea runtime.
			_ = recover()
		}()
		done <- cmd()
	}()
	select {
	case msg := <-done:
		return msg
	case <-time.After(drainTimeout):
		return nil
	}
}

// drain runs a command tree to completion, skipping timer-driven commands.
func drain(m tea.Model, cmd tea.Cmd, depth int) tea.Model {
	if cmd == nil || depth > 16 {
		return m
	}
	msg := runCmd(cmd)
	if msg == nil {
		return m
	}
	if batch, ok := msg.(tea.BatchMsg); ok {
		for _, c := range batch {
			m = drain(m, c, depth+1)
		}
		return m
	}
	if _, blink := msg.(cursor.BlinkMsg); blink {
		return m
	}
	next, nextCmd := m.Update(msg)
	return drain(next, nextCmd, depth+1)
}

// newTestModel builds a model pointed at a stub service.
func newTestModel(t *testing.T, baseURL string) *Model {
	t.Helper()
	m := New(Options{
		Client:   api.NewClient(baseURL),
		Settings: session.Settings{BaseURL: baseURL, Port: 8100},
	})
	// A realistic terminal, so width-dependent rendering is exercised rather
	// than the MinWidth fallback.
	m.width, m.height = 120, 40
	m.resize()
	return m
}

// press sends a key press and returns the resulting model and command.
func press(m *Model, key tea.KeyPressMsg) (*Model, tea.Cmd) {
	updated, cmd := m.Update(key)
	model, ok := updated.(*Model)
	if !ok {
		panic("Update returned a non-*Model")
	}
	return model, cmd
}

func pressRunes(text string) tea.KeyPressMsg {
	return tea.KeyPressMsg{Text: text, Code: rune(text[0])}
}

// --- the double-fire guard --------------------------------------------------

// TestKeyReleaseDoesNotAct is the regression guard for this workspace's known
// bug: bubbletea v2 delivers key RELEASES as well as presses, and acting on both
// fires every binding twice.
func TestKeyReleaseDoesNotAct(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	if m.menuCursor != 0 {
		t.Fatalf("menu cursor starts at %d, want 0", m.menuCursor)
	}

	updated, _ := m.Update(tea.KeyReleaseMsg{Text: "j", Code: 'j'})
	after, ok := updated.(*Model)
	if !ok {
		t.Fatalf("Update returned %T", updated)
	}
	if after.menuCursor != 0 {
		t.Errorf("a key RELEASE moved the menu cursor to %d; bindings would fire twice", after.menuCursor)
	}
}

// TestKeyPressDoesAct is the positive half: a press must still work.
func TestKeyPressDoesAct(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	m, _ = press(m, pressRunes("j"))
	if m.menuCursor != 1 {
		t.Errorf("menu cursor = %d after a press, want 1", m.menuCursor)
	}
	m, _ = press(m, pressRunes("k"))
	if m.menuCursor != 0 {
		t.Errorf("menu cursor = %d after pressing k, want 0", m.menuCursor)
	}
}

// TestMenuCursorStopsAtTheBounds keeps the selection on a real row.
func TestMenuCursorStopsAtTheBounds(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	m, _ = press(m, pressRunes("k"))
	if m.menuCursor != 0 {
		t.Errorf("cursor = %d after up at the top, want 0", m.menuCursor)
	}
	for i := 0; i < 50; i++ {
		m, _ = press(m, pressRunes("j"))
	}
	if want := len(menuItems()) - 1; m.menuCursor != want {
		t.Errorf("cursor = %d after running off the end, want %d", m.menuCursor, want)
	}
}

// TestNoTimerCommandIsEverReturned pins the design decision that keeps this
// suite fast: nothing in the model schedules a tick, so no drain can stall.
func TestNoTimerCommandIsEverReturned(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	if cmd := m.Init(); cmd != nil {
		t.Error("Init returned a command; opening the menu must not depend on the service")
	}
	// Navigation must not schedule anything either.
	cmd := tea.Cmd(nil)
	m, cmd = press(m, pressRunes("j"))
	if cmd != nil {
		t.Error("menu navigation returned a command")
	}
	m, cmd = press(m, pressRunes("k"))
	if cmd != nil {
		t.Error("menu navigation returned a command")
	}
}

// --- layout robustness ------------------------------------------------------

// TestRendersAtEveryWidthWithoutPanicking covers the negative-content-width
// class of bug: a layout helper that subtracts chrome from a tiny width used to
// panic (or silently produce a negative Repeat count) at narrow terminals.
func TestRendersAtEveryWidthWithoutPanicking(t *testing.T) {
	for width := 0; width <= 120; width++ {
		for _, s := range []screen{screenMenu, screenCircuits, screenSessions, screenLaps, screenCompare, screenStrategy, screenChat} {
			m := newTestModel(t, "http://127.0.0.1:1")
			m.width, m.height = width, 30
			m.screen = s
			m.resize()
			// A populated state is what actually exercises the width arithmetic.
			m.circuits = []api.Circuit{{CircuitID: "bahrain", CircuitName: "Bahrain International Circuit", Country: "Bahrain"}}
			m.sessions = []api.Session{{SessionID: "sim_2021_bahrain_r", SessionType: "race", Source: "sim", CircuitID: "bahrain"}}
			m.laps = []api.Lap{{LapID: "sim_2021_bahrain_l12", DriverID: "VER", LapNumber: 12}}
			m.comparison = &api.LapComparison{
				LapIDs:       []string{"a", "b"},
				Deltas:       []api.DeltaPoint{{DistanceM: 0, SpeedDelta: -12.5}, {DistanceM: 100, SpeedDelta: 8}},
				SectorDeltas: map[string][]float64{"sector1_ms": {30000, 29500}},
			}
			m.strategy = &api.StrategySim{TotalLaps: 53, NSims: 500, Strategies: []api.StrategySimStrategy{
				{Strategy: []string{"MEDIUM", "HARD"}, MedianRaceTimeS: 5100, WinProbability: 0.42, Rank: 1},
			}}
			m.chat = &api.ChatResponse{Response: "Brake later.", Trace: api.RetrievalTrace{Path: "agent"}}

			out := m.Render()
			if out == "" {
				t.Fatalf("width %d screen %d rendered nothing", width, s)
			}
			// No rendered line may be wider than the terminal, or the terminal
			// wraps and every box below it shifts.
			if width >= MinWidth {
				for i, line := range strings.Split(out, "\n") {
					if got := len([]rune(stripANSIForWidth(line))); got > width {
						t.Fatalf("width %d screen %d: line %d is %d cells wide: %q",
							width, s, i, got, line)
					}
				}
			}
		}
	}
}

// stripANSIForWidth removes SGR sequences so a rendered line can be measured in
// printable cells rather than bytes.
func stripANSIForWidth(s string) string {
	var b strings.Builder
	esc := false
	for _, r := range s {
		switch {
		case esc:
			if r == 'm' {
				esc = false
			}
		case r == 0x1b:
			esc = true
		default:
			b.WriteRune(r)
		}
	}
	return b.String()
}

// --- navigation -------------------------------------------------------------

// TestEscReturnsToTheMenuFromASubscreen keeps escape from quitting the program.
func TestEscReturnsToTheMenuFromASubscreen(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	m.screen = screenLaps
	m, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEsc})
	if m.screen != screenMenu {
		t.Errorf("screen = %v after esc, want the menu", m.screen)
	}
	if cmd != nil {
		if _, quit := cmd().(tea.QuitMsg); quit {
			t.Error("esc on a subscreen quit the program instead of returning to the menu")
		}
	}
}

// TestEscOnTheMenuQuits keeps the usual exit available.
func TestEscOnTheMenuQuits(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	_, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEsc})
	if cmd == nil {
		t.Fatal("esc on the menu returned no command")
	}
	if _, quit := cmd().(tea.QuitMsg); !quit {
		t.Error("esc on the menu did not quit")
	}
}

// TestOpeningCircuitsRequestsThem proves the menu action reaches the service.
func TestOpeningCircuitsRequestsThem(t *testing.T) {
	var path string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path = r.URL.Path
		_, _ = w.Write([]byte(`[{"circuit_id":"bahrain","circuit_name":"Bahrain","country":"Bahrain"}]`))
	}))
	defer server.Close()

	m := newTestModel(t, server.URL)
	// Move to the Circuits row.
	items := menuItems()
	for i, item := range items {
		if item.ID == menuCircuits {
			m.menuCursor = i
		}
	}
	m, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	if m.screen != screenCircuits {
		t.Fatalf("screen = %v, want circuits", m.screen)
	}
	m = drain(m, cmd, 0).(*Model)

	if path != "/api/circuits" {
		t.Errorf("requested %q, want /api/circuits", path)
	}
	if len(m.circuits) != 1 || m.circuits[0].CircuitID != "bahrain" {
		t.Errorf("circuits = %+v, want one Bahrain circuit", m.circuits)
	}
	if m.busy != "" {
		t.Errorf("busy = %q after a successful load, want it cleared", m.busy)
	}
}

// TestUnreachableServiceShowsTheStartHint keeps the most likely first-run
// failure actionable instead of showing a connection-refused string.
func TestUnreachableServiceShowsTheStartHint(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	for i, item := range menuItems() {
		if item.ID == menuCircuits {
			m.menuCursor = i
		}
	}
	m, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	m = drain(m, cmd, 0).(*Model)

	if m.failure == "" {
		t.Fatal("no failure message for an unreachable service")
	}
	for _, want := range []string{"docker compose up", "uvicorn api.main:app"} {
		if !strings.Contains(m.failure, want) {
			t.Errorf("failure does not mention %q:\n%s", want, m.failure)
		}
	}
}

// TestOracleDowngradeIsDistinguished keeps "service down" apart from
// "database down", because the two need different advice.
func TestOracleDowngradeIsDistinguished(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"detail":"ORA-12541: TNS:no listener"}`))
	}))
	defer server.Close()

	m := newTestModel(t, server.URL)
	for i, item := range menuItems() {
		if item.ID == menuCircuits {
			m.menuCursor = i
		}
	}
	m, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	m = drain(m, cmd, 0).(*Model)

	if !strings.Contains(m.failure, "Oracle") {
		t.Errorf("failure = %q, want it to name the database", m.failure)
	}
	if !strings.Contains(m.failure, "ORA-12541") {
		t.Errorf("failure = %q, want the service's own detail", m.failure)
	}
}

// --- form flows -------------------------------------------------------------

// TestCompareFormCompletesOnlyAfterItsCommandIsDrained pins the ordering rule:
// pressing enter does NOT finish a huh form in the same call, it returns a
// command that has to be processed first. Asserting before that drain is the
// mistake this test exists to prevent.
func TestCompareFormCompletesOnlyAfterItsCommandIsDrained(t *testing.T) {
	var requestedIDs string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/compare/laps" {
			requestedIDs = r.URL.Query().Get("ids")
			_, _ = w.Write([]byte(`{"lap_ids":["lap-a","lap-b"],"deltas":[{"distance_m":0,"speed_delta":-3}],` +
				`"sector_deltas":{"sector1_ms":[30000,29500]}}`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	m := newTestModel(t, server.URL)
	for i, item := range menuItems() {
		if item.ID == menuCompare {
			m.menuCursor = i
		}
	}
	m, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	m = drain(m, cmd, 0).(*Model)
	if m.form == nil {
		t.Fatal("the compare form did not open")
	}
	if m.formPurpose != purposeCompare {
		t.Fatalf("formPurpose = %v, want purposeCompare", m.formPurpose)
	}

	// Fill both lap ids. Every enter returns a command that advances the form to
	// the next field, so each one has to be drained before the next key is sent --
	// otherwise the following characters land in the field that is still focused.
	for _, r := range "lap-a" {
		m, _ = press(m, pressRunes(string(r)))
	}
	m, cmd = press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	m = drain(m, cmd, 0).(*Model)

	if m.form != nil && m.answers.LapA != "lap-a" {
		t.Fatalf("first field = %q after advancing, want lap-a", m.answers.LapA)
	}

	for _, r := range "lap-b" {
		m, _ = press(m, pressRunes(string(r)))
	}
	// Enter on the last field only returns the command that completes the form.
	m, cmd = press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	m = drain(m, cmd, 0).(*Model)

	if m.form != nil {
		t.Fatal("the form is still open after its completing command was drained")
	}
	if m.lapAID != "lap-a" || m.lapBID != "lap-b" {
		t.Errorf("answers = %q/%q, want lap-a/lap-b", m.lapAID, m.lapBID)
	}
	if m.failure != "" {
		t.Errorf("unexpected failure: %s", m.failure)
	}
	// The completing command must have issued the comparison for the two laps
	// that were actually typed, which is what proves the answers were bound.
	if requestedIDs != "lap-a,lap-b" {
		t.Errorf("requested ids = %q, want lap-a,lap-b", requestedIDs)
	}
	if m.screen != screenCompare {
		t.Errorf("screen = %v after a successful comparison, want the compare view", m.screen)
	}
}

// TestCompareAnsweringRefusesIdenticalLaps means the local check catches what the
// service would happily compare into a row of zeroes.
func TestCompareAnsweringRefusesIdenticalLaps(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	m.answers = Answers{LapA: "same", LapB: "same"}
	m.form = m.sized(CompareForm(&m.answers, "same", "same"))
	m.formPurpose = purposeCompare

	cmd := m.advance()
	if cmd != nil {
		t.Error("advance returned a command for an invalid pair")
	}
	if !strings.Contains(m.failure, "different laps") {
		t.Errorf("failure = %q, want it to explain the pair must differ", m.failure)
	}
}

// TestStrategyFormSeedIsAmongTheOptions is the guard for huh's silent fallback:
// a Select or MultiSelect seeded with a value that is not one of its options
// falls back to the first option, so a user asking for HARD would quietly get
// SOFT. The seed must be a subset of the options, always.
func TestStrategyFormSeedIsAmongTheOptions(t *testing.T) {
	answers := defaultStrategyAnswers()
	_ = StrategyForm(&Answers{}, &answers)

	options := map[string]bool{}
	for _, c := range CompoundOptions {
		options[c] = true
	}
	if len(answers.Compounds) == 0 {
		t.Fatal("the strategy form seeds no compounds")
	}
	for _, chosen := range answers.Compounds {
		if !options[chosen] {
			t.Fatalf("seeded compound %q is not among the options; huh would silently replace it", chosen)
		}
	}
}

// TestStrategyAnswersRequestAppliesDefaultsAndKeepsInRangeValues covers the
// typed-to-request conversion.
func TestStrategyAnswersRequestAppliesDefaultsAndKeepsInRangeValues(t *testing.T) {
	blank := StrategyAnswers{}
	got := blank.Request()
	if got.TotalLaps != 53 || got.NSims != 500 || got.TrackTempC != 30 || got.FuelStartKg != 110 {
		t.Errorf("blank answers produced %+v, want the service defaults", got)
	}
	if got.Compounds != nil {
		t.Errorf("blank answers set compounds = %v, want nil so the service picks", got.Compounds)
	}

	typed := StrategyAnswers{TotalLaps: "60", TrackTemp: "41.5", FuelKg: "95", NSims: "1200", Compounds: []string{"SOFT"}}
	got = typed.Request()
	if got.TotalLaps != 60 || got.TrackTempC != 41.5 || got.FuelStartKg != 95 || got.NSims != 1200 {
		t.Errorf("typed answers produced %+v", got)
	}
	if len(got.Compounds) != 1 || got.Compounds[0] != "SOFT" {
		t.Errorf("compounds = %v, want [SOFT]", got.Compounds)
	}
}

// TestStrategyFormValidatorsMirrorTheServiceBounds means an out-of-range value is
// caught in the form rather than coming back as an opaque 422.
func TestStrategyFormValidatorsMirrorTheServiceBounds(t *testing.T) {
	lapsValidator := validateNumericInRange("race distance", 2, 120, true)
	if err := lapsValidator(""); err != nil {
		t.Errorf("blank should mean default, got %v", err)
	}
	if err := lapsValidator("53"); err != nil {
		t.Errorf("53 rejected: %v", err)
	}
	for _, bad := range []string{"1", "121", "abc"} {
		if err := lapsValidator(bad); err == nil {
			t.Errorf("race distance %q was accepted", bad)
		}
	}

	tempValidator := validateNumericInRange("track temperature", 0, 60, false)
	if err := tempValidator("41.5"); err != nil {
		t.Errorf("41.5 rejected: %v", err)
	}
	for _, bad := range []string{"-1", "61"} {
		if err := tempValidator(bad); err == nil {
			t.Errorf("track temperature %q was accepted", bad)
		}
	}
}

// TestLapIDFormRejectsBlank keeps an empty answer from becoming a request.
func TestLapIDFormRejectsBlank(t *testing.T) {
	if err := requireNonBlank("a lap id")("   "); err == nil {
		t.Error("a blank lap id was accepted")
	}
	if err := requireNonBlank("a lap id")("sim_1"); err != nil {
		t.Errorf("a real lap id was rejected: %v", err)
	}
}

// TestEscapeAbortsAnOpenForm pins the fix for a real dead end: huh's default
// form keymap binds Quit to ctrl+c alone, so without this the user could only
// leave a form by finishing it -- while the footer advertised "esc cancel".
func TestEscapeAbortsAnOpenForm(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	for i, item := range menuItems() {
		if item.ID == menuStrategy {
			m.menuCursor = i
		}
	}
	m, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	m = drain(m, cmd, 0).(*Model)
	if m.form == nil {
		t.Fatal("the strategy form did not open")
	}

	m, cmd = press(m, tea.KeyPressMsg{Code: tea.KeyEsc})
	if m.form != nil {
		t.Fatal("escape left the form open; the only way out would be to finish it")
	}
	if m.formPurpose != purposeNone {
		t.Errorf("formPurpose = %v after cancelling, want purposeNone", m.formPurpose)
	}
	if !strings.Contains(m.notice, "Cancelled") {
		t.Errorf("notice = %q, want a cancellation message", m.notice)
	}
	if cmd != nil {
		if _, quit := cmd().(tea.QuitMsg); quit {
			t.Error("escaping a form quit the whole program instead of cancelling")
		}
	}
	if m.screen != screenMenu {
		t.Errorf("screen = %v after cancelling a form, want the menu", m.screen)
	}
}

// TestCtrlCStillQuitsWhileAFormIsOpen keeps a hard exit available mid-form.
func TestCtrlCStillQuitsWhileAFormIsOpen(t *testing.T) {
	m := newTestModel(t, "http://127.0.0.1:1")
	for i, item := range menuItems() {
		if item.ID == menuChat {
			m.menuCursor = i
		}
	}
	m, cmd := press(m, tea.KeyPressMsg{Code: tea.KeyEnter})
	m = drain(m, cmd, 0).(*Model)
	if m.form == nil {
		t.Fatal("the ask form did not open")
	}
	_, cmd = press(m, tea.KeyPressMsg{Code: 'c', Mod: tea.ModCtrl})
	if cmd == nil {
		t.Fatal("ctrl+c returned no command")
	}
	if _, quit := cmd().(tea.QuitMsg); !quit {
		t.Error("ctrl+c did not quit while a form was open")
	}
}

// --- helpers ----------------------------------------------------------------

// TestWrapPlainKeepsLongMessagesInsideTheWidth stops a long error from forcing
// the terminal to scroll sideways.
func TestWrapPlainKeepsLongMessagesInsideTheWidth(t *testing.T) {
	long := strings.Repeat("width ", 40)
	wrapped := wrapPlain(long, 40)
	for _, line := range strings.Split(wrapped, "\n") {
		if len([]rune(line)) > 40 {
			t.Fatalf("line is %d cells wide, want <= 40: %q", len([]rune(line)), line)
		}
	}
	// A narrow width is left alone rather than mangled.
	if got := wrapPlain("short", 5); got != "short" {
		t.Errorf("wrapPlain with a tiny width = %q, want the input unchanged", got)
	}
}

// TestBodyWidthNeverGoesNegative is the arithmetic guard behind the pane layout.
func TestBodyWidthNeverGoesNegative(t *testing.T) {
	for width := -5; width <= 30; width++ {
		m := &Model{width: width}
		if got := m.bodyWidth(); got < 1 {
			t.Fatalf("bodyWidth at terminal width %d = %d, want >= 1", width, got)
		}
		if got := m.listHeight(); got < 1 {
			t.Fatalf("listHeight at terminal width %d = %d, want >= 1", width, got)
		}
	}
}
