package session

import (
	"context"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// --- settings ---------------------------------------------------------------

// TestDefaultsPointAtTheDocumentedPort keeps the first run aligned with
// docker-compose.yml, which publishes the API on 8100.
func TestDefaultsPointAtTheDocumentedPort(t *testing.T) {
	d := Defaults()
	if d.Port != 8100 {
		t.Errorf("default port = %d, want 8100", d.Port)
	}
	if d.BaseURL != "http://127.0.0.1:8100" {
		t.Errorf("default base URL = %q", d.BaseURL)
	}
	if d.LaunchService {
		t.Error("LaunchService defaults to true; launching a service that needs Oracle should be opt-in")
	}
}

// TestNormalizeRepairsAHandEditedFile means a partial settings file cannot
// produce an empty URL or port 0.
func TestNormalizeRepairsAHandEditedFile(t *testing.T) {
	got := Settings{}.Normalize()
	if got.BaseURL != Defaults().BaseURL {
		t.Errorf("BaseURL = %q, want the default", got.BaseURL)
	}
	if got.Port != DefaultPort {
		t.Errorf("Port = %d, want %d", got.Port, DefaultPort)
	}
	bad := Settings{BaseURL: "http://x", Port: 70000}.Normalize()
	if bad.Port != DefaultPort {
		t.Errorf("Port = %d for an out-of-range value, want the default", bad.Port)
	}
}

// TestSaveThenLoadRoundTrips writes to a temp config dir so the real user config
// is never touched by a test.
func TestSaveThenLoadRoundTrips(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", dir)
	t.Setenv("HOME", dir)

	want := Settings{BaseURL: "http://127.0.0.1:8137", LaunchService: true, Port: 8137, ProjectRoot: "/tmp/repo"}
	if err := Save(want); err != nil {
		t.Fatalf("Save: %v", err)
	}

	path, err := ConfigPath()
	if err != nil {
		t.Fatalf("ConfigPath: %v", err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("stat %s: %v", path, err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("config permissions = %o, want 0600", perm)
	}

	got, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got != want {
		t.Errorf("round trip = %+v, want %+v", got, want)
	}
}

// TestLoadFallsBackWhenThereIsNoFile keeps a first run from erroring.
func TestLoadFallsBackWhenThereIsNoFile(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", dir)
	t.Setenv("HOME", dir)

	got, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got != Defaults() {
		t.Errorf("Load = %+v, want Defaults()", got)
	}
}

// TestSettingsCarryNoCredential is the security-relevant assertion: the file
// records a URL, not a secret, so a leaked copy reveals nothing usable.
func TestSettingsCarryNoCredential(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", dir)
	t.Setenv("HOME", dir)

	if err := Save(Defaults()); err != nil {
		t.Fatalf("Save: %v", err)
	}
	path, _ := ConfigPath()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	lower := strings.ToLower(string(raw))
	for _, forbidden := range []string{"password", "f1app", "secret", "token", "user"} {
		if strings.Contains(lower, forbidden) {
			t.Errorf("settings file contains %q: %s", forbidden, raw)
		}
	}
}

// --- launcher ---------------------------------------------------------------

// TestServerArgsCarryNoCredential guards the argv leak: /proc/<pid>/cmdline is
// world readable, so a secret here would be visible to every user on the box.
func TestServerArgsCarryNoCredential(t *testing.T) {
	argv := ServerArgs(8137)
	joined := strings.ToLower(strings.Join(argv, " "))
	for _, forbidden := range []string{"password", "secret", "token", "f1app"} {
		if strings.Contains(joined, forbidden) {
			t.Errorf("ServerArgs contains %q: %v", forbidden, argv)
		}
	}
}

// TestServerArgsMatchTheDocumentedCommand keeps the launcher on the interface
// CLAUDE.md documents, and off --reload (a reload manager spawns processes a TUI
// would then have to supervise).
func TestServerArgsMatchTheDocumentedCommand(t *testing.T) {
	argv := ServerArgs(8137)
	if argv[0] != "uv" || argv[1] != "run" || argv[2] != "uvicorn" {
		t.Errorf("argv = %v, want it to start uvicorn through uv", argv)
	}
	if argv[3] != "api.main:app" {
		t.Errorf("module = %q, want api.main:app", argv[3])
	}
	joined := strings.Join(argv, " ")
	if !strings.Contains(joined, "--port 8137") {
		t.Errorf("argv = %v, want the requested port", argv)
	}
	if strings.Contains(joined, "--reload") {
		t.Errorf("argv = %v, want no --reload", argv)
	}
}

// TestWaitForPortDetectsAnExitedChild is the fast-failure path: a child that died
// (almost always because Oracle is unreachable) must be reported in well under
// the poll timeout, not after it.
func TestWaitForPortDetectsAnExitedChild(t *testing.T) {
	start := time.Now()
	err := WaitForPort(context.Background(), "127.0.0.1", 1, 30*time.Second, func() bool { return true })
	if err == nil {
		t.Fatal("WaitForPort accepted a dead service")
	}
	if !strings.Contains(err.Error(), "exited") {
		t.Errorf("error = %v, want it to name the exit", err)
	}
	if elapsed := time.Since(start); elapsed > 5*time.Second {
		t.Errorf("took %s to notice the exit, want it to fail fast", elapsed)
	}
}

// TestWaitForPortTimesOutWhenNothingListens covers the "wrong URL" case.
func TestWaitForPortTimesOutWhenNothingListens(t *testing.T) {
	err := WaitForPort(context.Background(), "127.0.0.1", 1, 600*time.Millisecond, nil)
	if err == nil {
		t.Fatal("WaitForPort accepted a closed port")
	}
	if !strings.Contains(err.Error(), "did not accept connections") {
		t.Errorf("error = %v, want a timeout message", err)
	}
}

// TestWaitForPortHonoursCancellation keeps a ctrl-c responsive.
func TestWaitForPortHonoursCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := WaitForPort(ctx, "127.0.0.1", 1, 30*time.Second, nil); err == nil {
		t.Fatal("WaitForPort ignored a cancelled context")
	}
}

// TestWaitForPortSucceedsAgainstARealListener proves the poll actually detects a
// live socket rather than always timing out.
func TestWaitForPortSucceedsAgainstARealListener(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()
	port := ln.Addr().(*net.TCPAddr).Port

	if err := WaitForPort(context.Background(), "127.0.0.1", port, 5*time.Second, nil); err != nil {
		t.Fatalf("WaitForPort against a live listener: %v", err)
	}
}

// TestStartHintNamesTheRealCommands keeps first-run advice actionable.
func TestStartHintNamesTheRealCommands(t *testing.T) {
	hint := StartHint("http://127.0.0.1:8100")
	for _, want := range []string{"docker compose up", "uvicorn api.main:app", "--start-service", "http://127.0.0.1:8100"} {
		if !strings.Contains(hint, want) {
			t.Errorf("hint is missing %q:\n%s", want, hint)
		}
	}
}

// TestLaunchServerReportsAMissingBinary keeps a broken PATH diagnosable instead
// of panicking on a nil process.
func TestLaunchServerReportsAMissingBinary(t *testing.T) {
	// Save/restore the real PATH: an empty PATH makes `uv` unresolvable.
	original := os.Getenv("PATH")
	t.Cleanup(func() { _ = os.Setenv("PATH", original) })
	t.Setenv("PATH", filepath.Join(t.TempDir(), "empty"))

	server, err := LaunchServer(context.Background(), t.TempDir(), 8137)
	if err == nil {
		server.Stop()
		t.Fatal("LaunchServer started a binary that does not exist")
	}
	if !strings.Contains(err.Error(), "start") {
		t.Errorf("error = %v, want it to name the failed start", err)
	}
}
