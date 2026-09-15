package tui

import (
	"errors"
	"fmt"
	"strconv"
	"strings"

	"charm.land/huh/v2"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/huhstyle"
)

// formPurpose identifies which flow a completed form belongs to. It is stored on
// the model, so a form's answer is interpreted only after it has completed.
type formPurpose int

const (
	purposeNone formPurpose = iota
	purposeCompare
	purposeSimVsReal
	purposeTwin
	purposeStrategy
	purposeChat
)

// Answers holds the bound values of the currently open form.
//
// Every field is a pointer target for huh, so a single struct is reused across
// forms. Fields a given form does not show keep whatever the previous one left,
// which is why each form only reads the fields it bound.
type Answers struct {
	LapA     string
	LapB     string
	LapID    string
	Question string
}

// StrategyAnswers holds the strategy-simulation inputs.
type StrategyAnswers struct {
	TotalLaps string
	TrackTemp string
	FuelKg    string
	NSims     string
	Compounds []string
}

// CompoundOptions are the tyre compounds the service recognises. They match the
// StrategySimRequest default in api/models/schemas.py.
var CompoundOptions = []string{"SOFT", "MEDIUM", "HARD"}

func defaultStrategyAnswers() StrategyAnswers {
	return StrategyAnswers{
		TotalLaps: "53",
		TrackTemp: "30",
		FuelKg:    "110",
		NSims:     "500",
		Compounds: append([]string(nil), CompoundOptions...),
	}
}

// Request converts the typed answers into an api request, applying the same
// defaults the service uses.
//
// It is deliberately forgiving about blank input (falling back to the default)
// and strict about anything that parses but is out of range, so the error names
// the bound rather than reaching the service as a 422.
func (s StrategyAnswers) Request() api.StrategySimRequest {
	req := api.StrategySimRequest{
		TotalLaps:   parseIntOr(s.TotalLaps, 53),
		TrackTempC:  parseFloatOr(s.TrackTemp, 30),
		FuelStartKg: parseFloatOr(s.FuelKg, 110),
		NSims:       parseIntOr(s.NSims, 500),
		Seed:        42,
	}
	if len(s.Compounds) > 0 {
		req.Compounds = append([]string(nil), s.Compounds...)
	}
	return req
}

func parseIntOr(raw string, fallback int) int {
	v, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil {
		return fallback
	}
	return v
}

func parseFloatOr(raw string, fallback float64) float64 {
	v, err := strconv.ParseFloat(strings.TrimSpace(raw), 64)
	if err != nil {
		return fallback
	}
	return v
}

// themed wraps a form with the project-wide token theme and the accessible flag.
//
// WithAccessible is passed for correctness of intent, but note it only takes
// effect for a form run standalone via Form.Run: an EMBEDDED form (driven as a
// Bubble Tea component, which is what this package does) never consults it. That
// is why ACCESSIBLE also routes to the plain renderer instead of relying on this.
func themed(f *huh.Form) *huh.Form {
	return f.WithTheme(huh.ThemeFunc(huhstyle.Theme)).WithAccessible(huhstyle.Accessible())
}

// ValidateLapIDsDiffer rejects a comparison of a lap with itself, which the
// service would accept and then report as an all-zero delta.
func ValidateLapIDsDiffer(a, b string) error {
	if strings.TrimSpace(a) == strings.TrimSpace(b) {
		return errors.New("pick two different laps")
	}
	return nil
}

// validateNumericInRange builds a validator for a bounded number, mirroring the
// bounds the service enforces in api/models/schemas.py.
func validateNumericInRange(label string, min, max float64, integer bool) func(string) error {
	return func(raw string) error {
		trimmed := strings.TrimSpace(raw)
		if trimmed == "" {
			return nil // blank means "use the default"
		}
		var value float64
		var err error
		if integer {
			var parsed int
			parsed, err = strconv.Atoi(trimmed)
			value = float64(parsed)
		} else {
			value, err = strconv.ParseFloat(trimmed, 64)
		}
		if err != nil {
			return fmt.Errorf("%s must be a number", label)
		}
		if value < min || value > max {
			return fmt.Errorf("%s must be between %g and %g", label, min, max)
		}
		return nil
	}
}

// CompareForm asks for the two lap IDs to compare.
func CompareForm(ans *Answers, lapA, lapB string) *huh.Form {
	if ans.LapA == "" {
		ans.LapA = lapA
	}
	if ans.LapB == "" {
		ans.LapB = lapB
	}
	return themed(huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("First lap id").
				Description("the lap you are testing, for example sim_2021_bahrain_l12").
				Placeholder("lap id").
				Value(&ans.LapA).
				Validate(requireNonBlank("a lap id")),
			huh.NewInput().
				Title("Second lap id").
				Description("the reference lap to compare against").
				Placeholder("lap id").
				Value(&ans.LapB).
				Validate(func(v string) error {
					if err := requireNonBlank("a lap id")(v); err != nil {
						return err
					}
					return ValidateLapIDsDiffer(ans.LapA, v)
				}),
		).Title("Compare two laps"),
	))
}

// LapIDForm asks for a single lap id.
func LapIDForm(ans *Answers, title string) *huh.Form {
	return themed(huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title(title).
				Description("paste a lap id from the Laps screen").
				Placeholder("lap id").
				Value(&ans.LapID).
				Validate(requireNonBlank("a lap id")),
		).Title("Lap"),
	))
}

// AskForm asks the race engineer a question.
//
// A multi-line Text is used rather than an Input because a question about a lap
// is routinely longer than one terminal line.
func AskForm(ans *Answers) *huh.Form {
	return themed(huh.NewForm(
		huh.NewGroup(
			huh.NewText().
				Title("Ask the race engineer").
				Description("telemetry questions are answered from the database, with a retrieval trace").
				Placeholder("Where am I losing time in turn 4?").
				CharLimit(2000).
				Value(&ans.Question).
				Validate(requireNonBlank("a question")),
		).Title("Race engineer"),
	))
}

// StrategyForm collects the Monte Carlo inputs.
//
// The compounds MultiSelect is seeded with every option already selected, so the
// seed is guaranteed to be a subset of the options. That matters: a huh Select or
// MultiSelect whose seeded value is NOT among its options silently falls back to
// the first option, so a user who asked for HARD would quietly get SOFT. Keeping
// the seed inside the option set is the only safe construction, and
// TestStrategyFormSeedIsAmongTheOptions pins it.
func StrategyForm(ans *Answers, strategy *StrategyAnswers) *huh.Form {
	if len(strategy.Compounds) == 0 {
		strategy.Compounds = append([]string(nil), CompoundOptions...)
	}
	return themed(huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("Race distance (laps)").
				Description("2 to 120").
				Placeholder("53").
				Value(&strategy.TotalLaps).
				Validate(validateNumericInRange("race distance", 2, 120, true)),
			huh.NewInput().
				Title("Track temperature (C)").
				Description("0 to 60").
				Placeholder("30").
				Value(&strategy.TrackTemp).
				Validate(validateNumericInRange("track temperature", 0, 60, false)),
			huh.NewInput().
				Title("Starting fuel (kg)").
				Description("0 to 150").
				Placeholder("110").
				Value(&strategy.FuelKg).
				Validate(validateNumericInRange("starting fuel", 0, 150, false)),
			huh.NewInput().
				Title("Simulations per strategy").
				Description("50 to 5000; more runs, tighter percentiles").
				Placeholder("500").
				Value(&strategy.NSims).
				Validate(validateNumericInRange("simulations", 50, 5000, true)),
			huh.NewMultiSelect[string]().
				Title("Candidate compounds").
				Description("at least one").
				Options(huh.NewOptions(CompoundOptions...)...).
				Value(&strategy.Compounds).
				Validate(func(chosen []string) error {
					if len(chosen) == 0 {
						return errors.New("choose at least one compound")
					}
					return nil
				}),
		).Title("Strategy simulation"),
	))
}

// requireNonBlank rejects an empty or whitespace-only answer.
func requireNonBlank(what string) func(string) error {
	return func(v string) error {
		if strings.TrimSpace(v) == "" {
			return fmt.Errorf("enter %s", what)
		}
		return nil
	}
}

// menuItem is one row of the main menu.
type menuItem struct {
	ID    string
	Label string
	Hint  string
}

const (
	menuCompare   = "compare"
	menuSimVsReal = "sim-vs-real"
	menuTwin      = "twin"
	menuStrategy  = "strategy"
	menuChat      = "chat"
	menuCircuits  = "circuits"
	menuSessions  = "sessions"
	menuLaps      = "laps"
)

// menuItems is the main menu, ordered by how often a race engineer reaches for
// it: the two comparison flows first, then the raw listings.
func menuItems() []menuItem {
	return []menuItem{
		{ID: menuCompare, Label: "Compare two laps", Hint: "sector time deltas and speed traces"},
		{ID: menuSimVsReal, Label: "Sim vs real", Hint: "auto-match a sim lap to the closest real lap"},
		{ID: menuTwin, Label: "Driving twin", Hint: "which real driver your sim lap resembles, per sector"},
		{ID: menuStrategy, Label: "Strategy simulation", Hint: "Monte Carlo pit strategies, ranked by win probability"},
		{ID: menuChat, Label: "Ask the race engineer", Hint: "AI answers with a retrieval trace"},
		{ID: menuCircuits, Label: "Circuits", Hint: "tracks in the database"},
		{ID: menuSessions, Label: "Sessions", Hint: "sim, OpenF1 and Ergast sessions"},
		{ID: menuLaps, Label: "Laps", Hint: "laps with sector times; pick two to compare"},
	}
}
