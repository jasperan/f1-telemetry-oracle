// Package session holds the Go front-end's persisted connection settings and the
// one way it can start the project's own API.
//
// There are deliberately no credentials here. The API reads its Oracle user and
// password from its own environment (api/config.py, defaulting to f1app/f1app),
// so this front-end never sees a secret and has nothing to leak: the settings
// file records a URL and a port and nothing else.
package session

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// DefaultPort matches docker-compose.yml, which publishes the API on 8100.
const DefaultPort = 8100

// Settings are the persisted, non-secret connection settings.
type Settings struct {
	BaseURL       string `json:"base_url"`
	LaunchService bool   `json:"launch_service"`
	Port          int    `json:"port"`
	ProjectRoot   string `json:"project_root"`
}

// Defaults returns the settings a first run starts from.
//
// LaunchService defaults to false on purpose: starting the API requires Oracle
// to be reachable, and silently launching a process that will exit is worse than
// telling the user what to run.
func Defaults() Settings {
	return Settings{
		BaseURL:       "http://127.0.0.1:8100",
		LaunchService: false,
		Port:          DefaultPort,
	}
}

// ConfigPath is where Settings live. The file is written 0600.
func ConfigPath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", fmt.Errorf("locate config dir: %w", err)
	}
	return filepath.Join(dir, "f1-telemetry-oracle", "gotui.json"), nil
}

// Load reads Settings, falling back to Defaults when there is no file yet.
func Load() (Settings, error) {
	path, err := ConfigPath()
	if err != nil {
		return Defaults(), err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return Defaults(), nil
		}
		return Defaults(), fmt.Errorf("read %s: %w", path, err)
	}
	settings := Defaults()
	if err := json.Unmarshal(raw, &settings); err != nil {
		return Defaults(), fmt.Errorf("parse %s: %w", path, err)
	}
	return settings, nil
}

// Normalize fills in defaults for anything a hand-edited file left out, so a
// partial settings file can never produce an empty URL or port 0.
func (s Settings) Normalize() Settings {
	if strings.TrimSpace(s.BaseURL) == "" {
		s.BaseURL = Defaults().BaseURL
	}
	if s.Port <= 0 || s.Port > 65535 {
		s.Port = DefaultPort
	}
	return s
}

// Save writes Settings with 0600 permissions.
func Save(settings Settings) error {
	path, err := ConfigPath()
	if err != nil {
		return err
	}
	encoded, err := json.MarshalIndent(settings.Normalize(), "", "  ")
	if err != nil {
		return fmt.Errorf("encode settings: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("create %s: %w", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, append(encoded, '\n'), 0o600); err != nil {
		return fmt.Errorf("write %s: %w", path, err)
	}
	return nil
}

// ServerArgs is the exact argv used to start the API.
//
// It is exported so a test can assert that no credential can ever appear here.
// /proc/<pid>/cmdline is world readable, so a secret in argv would leak it to
// every user on the box regardless of file permissions.
//
// The command is the interface the repository already documents in CLAUDE.md
// ("uvicorn api.main:app --host 0.0.0.0 --port 8100"); --reload is deliberately
// omitted because a reload manager spawns extra processes for a TUI to supervise.
func ServerArgs(port int) []string {
	return []string{
		"uv", "run", "uvicorn", "api.main:app",
		"--host", "127.0.0.1",
		"--port", strconv.Itoa(port),
	}
}

// Server supervises a service process the TUI started.
type Server struct {
	cmd    *exec.Cmd
	stderr strings.Builder
	done   chan struct{}
}

// Stop terminates the whole process group, so a uvicorn worker cannot outlive it.
func (s *Server) Stop() {
	if s == nil || s.cmd == nil {
		return
	}
	_ = killProcessGroup(s.cmd)
	_, _ = s.cmd.Process.Wait()
}

// Stderr returns whatever the service logged, for error reporting.
func (s *Server) Stderr() string { return s.stderr.String() }

// LaunchServer starts the project's own API, using the command the repo already
// documents rather than reimplementing it. The child inherits this process's
// environment, so ORACLE_DSN/ORACLE_USER/ORACLE_PASSWORD reach it the same way
// they would from a shell.
//
// Note that uvicorn's lifespan opens an Oracle pool with min=2 connections
// (api/services/oracle.py), so if the database is not up the child exits almost
// immediately. That is why the caller must read Stderr() rather than assume a
// started process means a working service.
func LaunchServer(ctx context.Context, projectRoot string, port int) (*Server, error) {
	argv := ServerArgs(port)
	cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
	if projectRoot != "" {
		cmd.Dir = projectRoot
	}
	cmd.Env = os.Environ()

	server := &Server{cmd: cmd, done: make(chan struct{})}

	setProcessGroup(cmd)
	cmd.Cancel = func() error { return killProcessGroup(cmd) }
	// Bounds the wait for the pipes if a grandchild survives the signal.
	cmd.WaitDelay = 5 * time.Second

	cmd.Stdout = io.Discard
	cmd.Stderr = &server.stderr

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start %s: %w", strings.Join(argv[:3], " "), err)
	}
	go func() {
		_ = cmd.Wait()
		close(server.done)
	}()
	return server, nil
}

// Exited reports whether the child has already stopped, which for this service
// almost always means Oracle was unreachable.
func (s *Server) Exited() bool {
	if s == nil {
		return true
	}
	select {
	case <-s.done:
		return true
	default:
		return false
	}
}

// WaitForPort polls until the service accepts TCP connections, so the TUI shows a
// deterministic "starting" state instead of a connection error. It gives up early
// if the child exits, so a failed Oracle connection is reported in seconds rather
// than after the full timeout.
func WaitForPort(ctx context.Context, host string, port int, timeout time.Duration, exited func() bool) error {
	deadline := time.Now().Add(timeout)
	address := net.JoinHostPort(host, strconv.Itoa(port))
	for {
		conn, err := net.DialTimeout("tcp", address, 500*time.Millisecond)
		if err == nil {
			_ = conn.Close()
			return nil
		}
		if exited != nil && exited() {
			return fmt.Errorf("the service exited before it accepted connections on %s", address)
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("the service did not accept connections on %s within %s", address, timeout)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(250 * time.Millisecond):
		}
	}
}

// StartHint is the advice shown when the service cannot be reached. It names the
// commands the repository's own README documents, because the most likely cause
// is simply that the user has not started the stack yet.
func StartHint(baseURL string) string {
	return fmt.Sprintf(
		"No API at %s.\n"+
			"Start the stack first, from the repository root:\n"+
			"    docker compose up --build          # Oracle + API + frontend\n"+
			"or run just the API:\n"+
			"    uv run uvicorn api.main:app --host 127.0.0.1 --port 8100\n"+
			"Retry with --start-service to let this TUI launch the API for you.",
		baseURL)
}
