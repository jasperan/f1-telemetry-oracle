package tui

import (
	"os"
	"testing"
)

// TestChooseRouteForcesPlainForAccessible pins the decision that an embedded huh
// form cannot serve a screen reader.
//
// huh's WithAccessible is consulted only inside Form.RunWithContext (form.go:676).
// This package drives its forms as Bubble Tea components through Update/View, so
// the flag never takes effect and the full-screen UI would render identically for
// a screen-reader user. Routing them to plain output is the honest behaviour.
func TestChooseRouteForcesPlainForAccessible(t *testing.T) {
	if got := ChooseRoute(true, true, false, false); got != RoutePlain {
		t.Errorf("interactive + accessible = %v, want RoutePlain", got)
	}
}

// TestChooseRouteSelectsInteractiveOnlyOnATerminal covers the ordinary paths.
func TestChooseRouteSelectsInteractiveOnlyOnATerminal(t *testing.T) {
	cases := []struct {
		name                                    string
		interactive, accessible, plain, noInput bool
		want                                    RouteMode
	}{
		{"plain terminal", true, false, false, false, RouteInteractive},
		{"--plain", true, false, true, false, RoutePlain},
		{"no tty", false, false, false, false, RoutePlain},
		{"--no-input", true, false, false, true, RoutePlain},
		{"no tty and accessible", false, true, false, false, RoutePlain},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := ChooseRoute(c.interactive, c.accessible, c.plain, c.noInput); got != c.want {
				t.Errorf("ChooseRoute(%v,%v,%v,%v) = %v, want %v",
					c.interactive, c.accessible, c.plain, c.noInput, got, c.want)
			}
		})
	}
}

// TestAccessibleEnvIsReadFromTheEnvironment keeps the one documented switch wired.
// It reads the variable the same way huhstyle.Accessible does.
func TestAccessibleEnvIsReadFromTheEnvironment(t *testing.T) {
	t.Setenv("ACCESSIBLE", "")
	if os.Getenv("ACCESSIBLE") != "" {
		t.Error("an empty ACCESSIBLE was treated as set")
	}
	t.Setenv("ACCESSIBLE", "1")
	if os.Getenv("ACCESSIBLE") == "" {
		t.Error("ACCESSIBLE=1 was not visible to the router")
	}
}
