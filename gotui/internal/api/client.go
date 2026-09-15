package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// DefaultBaseURL is where the f1-telemetry-oracle API listens. It matches
// docker-compose.yml, which publishes the API on 8100.
const DefaultBaseURL = "http://127.0.0.1:8100"

// ErrUnreachable reports that the service could not be contacted at all. It is
// deliberately distinct from an HTTP error status so the UI can print "start
// the API" instead of a stack trace: the service is a separate process, and not
// running it is the single most likely first-run failure.
var ErrUnreachable = errors.New("f1-telemetry-oracle API unreachable")

// ErrOracleDown reports that the service answered but its database call failed.
// The API opens its Oracle pool at startup, so a connection error here means the
// database container is not up yet rather than that the URL is wrong.
var ErrOracleDown = errors.New("the API reached Oracle and the query failed")

// Client is a read-mostly client for the f1-telemetry-oracle FastAPI service.
type Client struct {
	baseURL string
	http    *http.Client
}

// NewClient builds a client for baseURL. A trailing slash is tolerated.
func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		// Strategy simulation is Monte Carlo over 50..5000 runs and the AI race
		// engineer calls a local LLM, so the ceiling is generous. It is still a
		// ceiling: a wedged request must not hang the UI forever.
		http: &http.Client{Timeout: 180 * time.Second},
	}
}

// BaseURL returns the configured service root.
func (c *Client) BaseURL() string { return c.baseURL }

// ValidateBaseURL rejects anything that is not an absolute http(s) URL with a
// host, so a typo is caught while typing rather than at request time.
func ValidateBaseURL(raw string) error {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return errors.New("a base URL is required")
	}
	u, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("not a valid URL: %w", err)
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return errors.New("use an http:// or https:// URL")
	}
	if u.Host == "" {
		return errors.New("the URL needs a host, for example 127.0.0.1:8100")
	}
	return nil
}

// do performs a request and decodes a JSON body into out.
func (c *Client) do(ctx context.Context, method, path string, body any, out any) error {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encode request: %w", err)
		}
		reader = bytes.NewReader(encoded)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrUnreachable, err)
	}
	defer resp.Body.Close()

	payload, err := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if err != nil {
		return fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		return classifyHTTPError(method, path, resp.StatusCode, payload)
	}

	if out == nil {
		return nil
	}
	if err := json.Unmarshal(payload, out); err != nil {
		return fmt.Errorf("decode %s body: %w", path, err)
	}
	return nil
}

// classifyHTTPError turns a non-2xx response into a message a user can act on.
//
// A 500 from these routes means an Oracle or Ollama call threw, so it is
// labelled with ErrOracleDown to keep the "start the database" guidance
// separate from "your request was wrong".
func classifyHTTPError(method, path string, status int, payload []byte) error {
	msg := fmt.Sprintf("%s %s: HTTP %d: %s", method, path, status, detail(payload))
	if status >= 500 {
		return fmt.Errorf("%w: %s", ErrOracleDown, msg)
	}
	return errors.New(msg)
}

// detail pulls FastAPI's {"detail": ...} string, falling back to a truncated
// body so an unexpected error page is still diagnosable.
func detail(payload []byte) string {
	var envelope struct {
		Detail any `json:"detail"`
	}
	if err := json.Unmarshal(payload, &envelope); err == nil && envelope.Detail != nil {
		if s, ok := envelope.Detail.(string); ok {
			return s
		}
		if encoded, err := json.Marshal(envelope.Detail); err == nil {
			return string(encoded)
		}
	}
	trimmed := strings.TrimSpace(string(payload))
	if len(trimmed) > 300 {
		trimmed = trimmed[:300] + "..."
	}
	if trimmed == "" {
		return "(empty response)"
	}
	return trimmed
}

// Health calls GET /health. It is the cheapest way to tell "service not
// running" apart from "service running but Oracle is not up".
func (c *Client) Health(ctx context.Context) (*HealthResponse, error) {
	var out HealthResponse
	if err := c.do(ctx, http.MethodGet, "/health", nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Circuits calls GET /api/circuits.
func (c *Client) Circuits(ctx context.Context, limit int) ([]Circuit, error) {
	if limit <= 0 {
		limit = 100
	}
	var out []Circuit
	if err := c.do(ctx, http.MethodGet, fmt.Sprintf("/api/circuits?limit=%d", limit), nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// Sessions calls GET /api/sessions with an optional source filter
// ("sim", "openf1" or "ergast"). An empty source asks for all of them.
func (c *Client) Sessions(ctx context.Context, source string, limit int) ([]Session, error) {
	if limit <= 0 {
		limit = 100
	}
	path := fmt.Sprintf("/api/sessions?limit=%d", limit)
	if strings.TrimSpace(source) != "" {
		path += "&source=" + url.QueryEscape(strings.TrimSpace(source))
	}
	var out []Session
	if err := c.do(ctx, http.MethodGet, path, nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// Drivers calls GET /api/drivers, optionally filtered by nationality.
func (c *Client) Drivers(ctx context.Context, nationality string, limit int) ([]Driver, error) {
	if limit <= 0 {
		limit = 100
	}
	path := fmt.Sprintf("/api/drivers?limit=%d", limit)
	if strings.TrimSpace(nationality) != "" {
		path += "&nationality=" + url.QueryEscape(strings.TrimSpace(nationality))
	}
	var out []Driver
	if err := c.do(ctx, http.MethodGet, path, nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// Laps calls GET /api/laps, filtered by session and/or driver.
func (c *Client) Laps(ctx context.Context, sessionID, driverID string, limit int) ([]Lap, error) {
	if limit <= 0 {
		limit = 100
	}
	path := fmt.Sprintf("/api/laps?limit=%d", limit)
	if strings.TrimSpace(sessionID) != "" {
		path += "&session_id=" + url.QueryEscape(strings.TrimSpace(sessionID))
	}
	if strings.TrimSpace(driverID) != "" {
		path += "&driver_id=" + url.QueryEscape(strings.TrimSpace(driverID))
	}
	var out []Lap
	if err := c.do(ctx, http.MethodGet, path, nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// CompareLaps calls GET /api/compare/laps?ids=a,b. The service requires at least
// two IDs and only aligns the first two, so that is enforced here too.
func (c *Client) CompareLaps(ctx context.Context, lapIDs []string) (*LapComparison, error) {
	ids := make([]string, 0, len(lapIDs))
	for _, id := range lapIDs {
		if trimmed := strings.TrimSpace(id); trimmed != "" {
			ids = append(ids, trimmed)
		}
	}
	if len(ids) < 2 {
		return nil, errors.New("comparing laps needs at least two lap IDs")
	}
	path := "/api/compare/laps?ids=" + url.QueryEscape(strings.Join(ids, ","))
	var out LapComparison
	if err := c.do(ctx, http.MethodGet, path, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// SimVsReal calls GET /api/compare/sim-vs-real. The service rejects a lap whose
// session source is not "sim" with a 400, which surfaces as a clear message.
func (c *Client) SimVsReal(ctx context.Context, lapID string) (*SimVsReal, error) {
	if strings.TrimSpace(lapID) == "" {
		return nil, errors.New("a sim lap id is required")
	}
	path := "/api/compare/sim-vs-real?lap_id=" + url.QueryEscape(strings.TrimSpace(lapID))
	var out SimVsReal
	if err := c.do(ctx, http.MethodGet, path, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// DrivingTwin calls GET /api/compare/driving-twin.
func (c *Client) DrivingTwin(ctx context.Context, lapID string, topK int) (*DrivingTwin, error) {
	if strings.TrimSpace(lapID) == "" {
		return nil, errors.New("a sim lap id is required")
	}
	if topK <= 0 {
		topK = 5
	}
	if topK > 20 {
		topK = 20
	}
	path := fmt.Sprintf("/api/compare/driving-twin?lap_id=%s&top_k=%d",
		url.QueryEscape(strings.TrimSpace(lapID)), topK)
	var out DrivingTwin
	if err := c.do(ctx, http.MethodGet, path, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StrategySim calls POST /api/predict/strategy-sim.
func (c *Client) StrategySim(ctx context.Context, req StrategySimRequest) (*StrategySim, error) {
	if err := ValidateStrategySim(req); err != nil {
		return nil, err
	}
	var out StrategySim
	if err := c.do(ctx, http.MethodPost, "/api/predict/strategy-sim", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ValidateStrategySim mirrors the service's own Field bounds. Checking here means
// a bad value is reported next to the field instead of coming back as a 422.
func ValidateStrategySim(req StrategySimRequest) error {
	if req.TotalLaps < 2 || req.TotalLaps > 120 {
		return fmt.Errorf("total laps must be between 2 and 120, got %d", req.TotalLaps)
	}
	if req.TrackTempC < 0 || req.TrackTempC > 60 {
		return fmt.Errorf("track temperature must be between 0 and 60 C, got %g", req.TrackTempC)
	}
	if req.FuelStartKg < 0 || req.FuelStartKg > 150 {
		return fmt.Errorf("starting fuel must be between 0 and 150 kg, got %g", req.FuelStartKg)
	}
	if req.NSims < 50 || req.NSims > 5000 {
		return fmt.Errorf("simulations must be between 50 and 5000, got %d", req.NSims)
	}
	return nil
}

// Chat calls POST /api/chat/message (the AI race engineer).
func (c *Client) Chat(ctx context.Context, req ChatRequest) (*ChatResponse, error) {
	if strings.TrimSpace(req.Message) == "" {
		return nil, errors.New("the question is empty")
	}
	var out ChatResponse
	if err := c.do(ctx, http.MethodPost, "/api/chat/message", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
