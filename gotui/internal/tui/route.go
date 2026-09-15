package tui

// RouteMode is how the caller should present results.
type RouteMode int

const (
	// RouteInteractive opens the full-screen UI.
	RouteInteractive RouteMode = iota
	// RoutePlain prints text and never opens a form.
	RoutePlain
)

// ChooseRoute decides between the full-screen UI and plain output.
//
// The accessible flag forces RoutePlain. That is not a convenience: huh's
// WithAccessible is only consulted inside Form.RunWithContext, and this app
// embeds its forms as Bubble Tea components, so the option is inert here. An
// accessible user would get a full-screen UI that renders no differently and
// cannot be read, which is worse than a plain one. The canonical note in
// docs/huh/huhstyle.go says the same thing, so this follows it rather than
// pretending otherwise.
//
// NoInput also forces RoutePlain-with-refusal at the call site: with no terminal
// there is nobody to answer a prompt, and a form attached to a pipe would sit
// until the pipe closed.
func ChooseRoute(interactive, accessible, plain, noInput bool) RouteMode {
	if accessible || plain || noInput || !interactive {
		return RoutePlain
	}
	return RouteInteractive
}
