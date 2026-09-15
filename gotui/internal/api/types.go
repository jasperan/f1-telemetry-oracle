// Package api is a thin client for the f1-telemetry-oracle FastAPI service.
//
// Every value here mirrors a response model the service already defines in
// api/models/schemas.py. Nothing is computed locally: a Go user and a browser
// user see the same numbers, because both read the same endpoints.
package api

// HealthResponse is GET /health.
type HealthResponse struct {
	Status string `json:"status"`
}

// Circuit mirrors api.models.schemas.CircuitResponse.
type Circuit struct {
	CircuitID    string   `json:"circuit_id"`
	CircuitName  string   `json:"circuit_name"`
	Country      string   `json:"country"`
	Locality     *string  `json:"locality"`
	TrackLengthM *float64 `json:"track_length_m"`
	Lat          *float64 `json:"lat"`
	Lng          *float64 `json:"lng"`
	CreatedAt    *string  `json:"created_at"`
}

// DisplayName is the circuit label used in lists.
func (c Circuit) DisplayName() string {
	if c.CircuitName != "" {
		return c.CircuitName
	}
	return c.CircuitID
}

// Session mirrors api.models.schemas.SessionResponse.
type Session struct {
	SessionID   string   `json:"session_id"`
	CircuitID   string   `json:"circuit_id"`
	SessionType string   `json:"session_type"`
	Source      string   `json:"source"`
	Season      *int     `json:"season"`
	RoundNumber *int     `json:"round_number"`
	AirTempC    *float64 `json:"air_temp_c"`
	TrackTempC  *float64 `json:"track_temp_c"`
	StartedAt   *string  `json:"started_at"`
	CreatedAt   *string  `json:"created_at"`
}

// Driver mirrors api.models.schemas.DriverResponse.
type Driver struct {
	DriverID     string  `json:"driver_id"`
	Code         *string `json:"code"`
	FirstName    string  `json:"first_name"`
	LastName     string  `json:"last_name"`
	DriverNumber *int    `json:"driver_number"`
	Nationality  *string `json:"nationality"`
	IsSimPlayer  bool    `json:"is_sim_player"`
	CreatedAt    *string `json:"created_at"`
}

// Name is the driver label used in lists.
func (d Driver) Name() string {
	if d.Code != nil && *d.Code != "" {
		return *d.Code
	}
	full := d.FirstName + " " + d.LastName
	if full != " " {
		return full
	}
	return d.DriverID
}

// Lap mirrors api.models.schemas.LapResponse.
type Lap struct {
	LapID        string   `json:"lap_id"`
	SessionID    string   `json:"session_id"`
	DriverID     string   `json:"driver_id"`
	LapNumber    int      `json:"lap_number"`
	Sector1Ms    *int     `json:"sector1_ms"`
	Sector2Ms    *int     `json:"sector2_ms"`
	Sector3Ms    *int     `json:"sector3_ms"`
	LapTimeMs    *int     `json:"lap_time_ms"`
	TireCompound *string  `json:"tire_compound"`
	TireAgeLaps  *int     `json:"tire_age_laps"`
	FuelLoadKg   *float64 `json:"fuel_load_kg"`
	ErsDeployPct *float64 `json:"ers_deploy_pct"`
	IsValid      bool     `json:"is_valid"`
	Position     *int     `json:"position"`
	CreatedAt    *string  `json:"created_at"`
}

// DeltaPoint mirrors api.models.schemas.DeltaPoint.
//
// Every field is lap A minus lap B at one distance step, so a positive
// SpeedDelta means the first lap was faster there.
type DeltaPoint struct {
	DistanceM     float64 `json:"distance_m"`
	SpeedDelta    float64 `json:"speed_delta"`
	ThrottleDelta float64 `json:"throttle_delta"`
	BrakeDelta    float64 `json:"brake_delta"`
	SteeringDelta float64 `json:"steering_delta"`
}

// LapComparison mirrors api.models.schemas.LapComparisonResponse.
//
// SectorDeltas is named "deltas" by the service but actually holds each lap's
// raw sector time: {"sector1_ms": [lapA, lapB, ...]}. The difference is
// computed client-side; see analysis.SectorDeltas.
type LapComparison struct {
	LapIDs       []string             `json:"lap_ids"`
	Deltas       []DeltaPoint         `json:"deltas"`
	SectorDeltas map[string][]float64 `json:"sector_deltas"`
}

// SimVsReal mirrors api.models.schemas.SimVsRealResponse.
type SimVsReal struct {
	SimLapID   string        `json:"sim_lap_id"`
	RealLapID  string        `json:"real_lap_id"`
	CircuitID  string        `json:"circuit_id"`
	Comparison LapComparison `json:"comparison"`
}

// TwinMatch is one vector-similarity hit inside a sector.
type TwinMatch struct {
	LapID      string  `json:"lap_id"`
	Code       string  `json:"code"`
	Driver     string  `json:"driver"`
	LapTimeMs  *int    `json:"lap_time_ms"`
	Similarity float64 `json:"similarity"`
}

// TwinSector is one sector's ranked matches.
type TwinSector struct {
	Sector  int         `json:"sector"`
	Matches []TwinMatch `json:"matches"`
}

// TwinDriver is the aggregated "you drive like" verdict.
type TwinDriver struct {
	DriverCode           string  `json:"driver_code"`
	MeanSimilarity       float64 `json:"mean_similarity"`
	BestSectorSimilarity float64 `json:"best_sector_similarity"`
}

// DrivingTwin is GET /api/compare/driving-twin. The service returns a free-form
// object, so this mirrors api/services/driving.py's actual keys.
type DrivingTwin struct {
	LapID       string       `json:"lap_id"`
	Error       string       `json:"error"`
	OverallTwin *TwinDriver  `json:"overall_twin"`
	Sectors     []TwinSector `json:"sectors"`
}

// StrategySimRequest is the POST body for /api/predict/strategy-sim.
//
// Bounds mirror the service's own Field constraints so an out-of-range value is
// rejected in the form rather than by an HTTP 422.
type StrategySimRequest struct {
	TotalLaps   int      `json:"total_laps"`
	TrackTempC  float64  `json:"track_temp_c"`
	FuelStartKg float64  `json:"fuel_start_kg"`
	NSims       int      `json:"n_sims"`
	Seed        int      `json:"seed"`
	Compounds   []string `json:"compounds,omitempty"`
}

// StrategySimStrategy is one ranked pit strategy.
type StrategySimStrategy struct {
	Strategy        []string `json:"strategy"`
	MedianRaceTimeS float64  `json:"median_race_time_s"`
	P10RaceTimeS    float64  `json:"p10_race_time_s"`
	P90RaceTimeS    float64  `json:"p90_race_time_s"`
	WinProbability  float64  `json:"win_probability"`
	Rank            int      `json:"rank"`
}

// StrategySim mirrors api.models.schemas.StrategySimResponse.
type StrategySim struct {
	TotalLaps      int                   `json:"total_laps"`
	TrackTempC     float64               `json:"track_temp_c"`
	NSims          int                   `json:"n_sims"`
	FastestMedianS float64               `json:"fastest_median_s"`
	Strategies     []StrategySimStrategy `json:"strategies"`
}

// ChatRequest is the POST body for /api/chat/message.
type ChatRequest struct {
	Message          string  `json:"message"`
	SessionID        *string `json:"session_id,omitempty"`
	IncludeTelemetry bool    `json:"include_telemetry"`
}

// RetrievalTrace mirrors api.routers.chat.RetrievalTrace.
type RetrievalTrace struct {
	Path       string         `json:"path"`
	Intent     *string        `json:"intent"`
	Entities   map[string]any `json:"entities"`
	ToolCalls  []string       `json:"tool_calls"`
	Iterations int            `json:"iterations"`
	Sources    map[string]int `json:"sources"`
	StagesMs   map[string]int `json:"stages_ms"`
}

// ChatResponse mirrors api.routers.chat.ChatResponse.
type ChatResponse struct {
	Response  string         `json:"response"`
	Intent    string         `json:"intent"`
	Entities  map[string]any `json:"entities"`
	Sources   map[string]int `json:"sources"`
	ElapsedMs int            `json:"elapsed_ms"`
	Trace     RetrievalTrace `json:"trace"`
}
