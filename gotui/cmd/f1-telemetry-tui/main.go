// Command f1-telemetry-tui is an additional way to run f1-telemetry-oracle: a Go
// front-end in the charm v2 + huh stack that talks to the same FastAPI service
// the Next.js dashboard and the Python collectors use.
//
// It never reimplements telemetry analysis. Every lap, sector time, similarity,
// strategy and answer comes from the project's own API, so a terminal user and a
// browser user get identical results. The only derived work it does is
// presentation: differencing the raw per-lap sector times the compare endpoint
// returns, and bucketing distance-aligned speed deltas into readable segments.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	tea "charm.land/bubbletea/v2"

	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/api"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/huhstyle"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/session"
	"github.com/jasperan/f1-telemetry-oracle/gotui/internal/tui"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "f1-telemetry-tui: "+err.Error())
		os.Exit(1)
	}
}

// options are the parsed command line.
type options struct {
	baseURL      string
	port         int
	startService bool
	plain        bool
	jsonOut      bool
	noInput      bool
	projectRoot  string

	health   bool
	circuits bool
	sessions bool
	source   string
	laps     bool
	lapSess  string
	driver   string

	compare   string
	simVsReal string
	twin      string

	strategySim bool
	totalLaps   int
	trackTemp   float64
	fuelKg      float64
	nSims       int

	ask string
}

func run() error {
	saved, err := session.Load()
	if err != nil {
		// A broken settings file is not fatal: fall back to defaults so the user
		// still gets a usable tool.
		saved = session.Defaults()
	}
	saved = saved.Normalize()

	var opts options
	flag.StringVar(&opts.baseURL, "base-url", saved.BaseURL, "f1-telemetry-oracle API base URL")
	flag.IntVar(&opts.port, "port", saved.Port, "port used when starting the API")
	flag.BoolVar(&opts.startService, "start-service", saved.LaunchService, "start the repo's API (uv run uvicorn api.main:app) before connecting")
	flag.BoolVar(&opts.plain, "plain", false, "never open the full-screen UI; print plain text")
	flag.BoolVar(&opts.jsonOut, "json", false, "print the service's JSON verbatim instead of formatted text")
	flag.BoolVar(&opts.noInput, "no-input", false, "never prompt; fail instead")
	flag.StringVar(&opts.projectRoot, "project-root", "", "repository checkout used by --start-service")

	flag.BoolVar(&opts.health, "health", false, "check the API and exit")
	flag.BoolVar(&opts.circuits, "circuits", false, "list circuits and exit")
	flag.BoolVar(&opts.sessions, "sessions", false, "list sessions and exit")
	flag.StringVar(&opts.source, "source", "", "with --sessions, filter by source: sim, openf1, ergast")
	flag.BoolVar(&opts.laps, "laps", false, "list laps and exit")
	flag.StringVar(&opts.lapSess, "session", "", "with --laps, filter by session id")
	flag.StringVar(&opts.driver, "driver", "", "with --laps, filter by driver id")

	flag.StringVar(&opts.compare, "compare", "", "compare two laps: --compare lapA,lapB")
	flag.StringVar(&opts.simVsReal, "sim-vs-real", "", "match a sim lap to the closest real lap: --sim-vs-real LAP")
	flag.StringVar(&opts.twin, "driving-twin", "", "which real driver a sim lap resembles: --driving-twin LAP")

	flag.BoolVar(&opts.strategySim, "strategy-sim", false, "run the Monte Carlo pit strategy simulation")
	flag.IntVar(&opts.totalLaps, "laps-total", 53, "with --strategy-sim, race distance in laps (2-120)")
	flag.Float64Var(&opts.trackTemp, "track-temp", 30, "with --strategy-sim, track temperature in C (0-60)")
	flag.Float64Var(&opts.fuelKg, "fuel", 110, "with --strategy-sim, starting fuel in kg (0-150)")
	flag.IntVar(&opts.nSims, "sims", 500, "with --strategy-sim, simulations per strategy (50-5000)")

	flag.StringVar(&opts.ask, "ask", "", "ask the AI race engineer a question and exit")
	flag.Parse()

	// A negative port or an unparsable URL is caught before any request.
	if err := api.ValidateBaseURL(opts.baseURL); err != nil {
		return fmt.Errorf("--base-url: %w", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Bring the project's own API up first when asked, so every path below sees a
	// live service or a clear reason why not.
	var server *session.Server
	if opts.startService {
		root := opts.projectRoot
		if root == "" {
			root = detectProjectRoot()
		}
		port := opts.port
		var err error
		server, err = session.LaunchServer(ctx, root, port)
		if err != nil {
			return fmt.Errorf("--start-service: %w", err)
		}
		defer server.Stop()

		if err := session.WaitForPort(ctx, "127.0.0.1", port, 30*time.Second, server.Exited); err != nil {
			// The most common cause is that Oracle is not up: uvicorn's lifespan
			// opens an eager pool (min=2 connections) and exits immediately if the
			// database is unreachable. Surface the child's own log, which says so.
			return fmt.Errorf("%w\n%s\n%s", err,
				strings.TrimSpace(lastLines(server.Stderr(), 12)),
				session.StartHint(opts.baseURL))
		}
	}

	client := api.NewClient(opts.baseURL)

	// Scripted actions never open a TUI: they are the pipeable, automatable form.
	if action := scriptedAction(opts); action != "" {
		return runScripted(ctx, client, opts)
	}

	// No action and no usable terminal means there is nobody to drive a form.
	// Refusing with the exact commands to run beats opening a UI that can never be
	// read. This also covers ACCESSIBLE: an embedded huh form ignores
	// WithAccessible, so screen-reader users get the plain path instead.
	if tui.ChooseRoute(huhstyle.Interactive(), huhstyle.Accessible(), opts.plain, opts.noInput) == tui.RoutePlain {
		return errors.New("no usable terminal and no action requested.\n" +
			"Run one of: --health, --circuits, --sessions, --laps, --compare A,B,\n" +
			"            --sim-vs-real LAP, --driving-twin LAP, --strategy-sim, --ask QUESTION\n" +
			"or run it from a terminal for the full-screen UI.\n" +
			"(ACCESSIBLE=1 selects plain output: the embedded forms cannot serve a screen reader.)")
	}

	model := tui.New(tui.Options{
		Client:     client,
		Settings:   session.Settings{BaseURL: opts.baseURL, Port: opts.port},
		Plain:      opts.plain,
		Accessible: huhstyle.Accessible(),
	})
	if _, err := tea.NewProgram(model).Run(); err != nil {
		return fmt.Errorf("run the TUI: %w", err)
	}
	return nil
}

// scriptedAction names the one-shot action that was requested, or "" when the
// caller wants the interactive UI.
func scriptedAction(opts options) string {
	switch {
	case opts.health:
		return "health"
	case opts.circuits:
		return "circuits"
	case opts.sessions:
		return "sessions"
	case opts.laps:
		return "laps"
	case opts.compare != "":
		return "compare"
	case opts.simVsReal != "":
		return "sim-vs-real"
	case opts.twin != "":
		return "driving-twin"
	case opts.strategySim:
		return "strategy-sim"
	case opts.ask != "":
		return "ask"
	}
	return ""
}

// runScripted performs a one-shot action and prints the result.
func runScripted(ctx context.Context, client *api.Client, opts options) error {
	action := scriptedAction(opts)

	switch action {
	case "health":
		health, err := client.Health(ctx)
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(health)
		}
		fmt.Print(tui.PlainHealth(client.BaseURL(), health))
		return nil

	case "circuits":
		circuits, err := client.Circuits(ctx, 100)
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(circuits)
		}
		fmt.Print(tui.PlainCircuits(circuits))
		return nil

	case "sessions":
		sessions, err := client.Sessions(ctx, opts.source, 100)
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(sessions)
		}
		fmt.Print(tui.PlainSessions(sessions))
		return nil

	case "laps":
		laps, err := client.Laps(ctx, opts.lapSess, opts.driver, 100)
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(laps)
		}
		fmt.Print(tui.PlainLaps(laps))
		return nil

	case "compare":
		ids := strings.Split(opts.compare, ",")
		if len(ids) != 2 {
			return fmt.Errorf("--compare needs exactly two lap ids separated by a comma, got %q", opts.compare)
		}
		comparison, err := client.CompareLaps(ctx, ids)
		if err != nil {
			return err
		}
		// The service returns its bytes; --json forwards the decoded value so a
		// caller can rely on the documented field names rather than our re-encoding.
		if opts.jsonOut {
			return printJSON(comparison)
		}
		fmt.Print(tui.PlainComparison(comparison, strings.TrimSpace(ids[0]), strings.TrimSpace(ids[1])))
		return nil

	case "sim-vs-real":
		result, err := client.SimVsReal(ctx, opts.simVsReal)
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(result)
		}
		fmt.Print(tui.PlainSimVsReal(result))
		return nil

	case "driving-twin":
		result, err := client.DrivingTwin(ctx, opts.twin, 5)
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(result)
		}
		fmt.Print(tui.PlainTwin(result))
		return nil

	case "strategy-sim":
		req := api.StrategySimRequest{
			TotalLaps:   opts.totalLaps,
			TrackTempC:  opts.trackTemp,
			FuelStartKg: opts.fuelKg,
			NSims:       opts.nSims,
			Seed:        42,
		}
		result, err := client.StrategySim(ctx, req)
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(result)
		}
		fmt.Print(tui.PlainStrategy(result))
		return nil

	case "ask":
		answer, err := client.Chat(ctx, api.ChatRequest{Message: opts.ask, IncludeTelemetry: true})
		if err != nil {
			return err
		}
		if opts.jsonOut {
			return printJSON(answer)
		}
		fmt.Print(tui.PlainChat(answer))
		return nil
	}
	return fmt.Errorf("unknown action %q", action)
}

// printJSON writes a value as indented JSON.
func printJSON(v any) error {
	encoded, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return fmt.Errorf("encode json: %w", err)
	}
	fmt.Println(string(encoded))
	return nil
}

// detectProjectRoot walks up from the working directory looking for the marker
// files that identify this repo, so --start-service works when run from inside
// the checkout without an explicit --project-root.
func detectProjectRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		return ""
	}
	for {
		if _, err := os.Stat(dir + "/api/main.py"); err == nil {
			return dir
		}
		parent := dir[:strings.LastIndex(dir, "/")]
		if parent == "" || parent == dir {
			return ""
		}
		dir = parent
	}
}

// lastLines returns the final n lines of a log, which is where uvicorn puts the
// exception that explains why it refused to start.
func lastLines(text string, n int) string {
	lines := strings.Split(strings.TrimRight(text, "\n"), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return strings.Join(lines, "\n")
}
