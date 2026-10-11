package workers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go-app/config"
)

func TestServeBacktestOptimize_Validation(t *testing.T) {
	cfg := &config.Config{}

	// Test 1: Method Not Allowed
	req := httptest.NewRequest(http.MethodGet, "/api/backtest/optimize", nil)
	w := httptest.NewRecorder()
	ServeBacktestOptimize(cfg, w, req)
	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected status 405, got %d", w.Code)
	}

	// Test 2: Invalid Strategy
	body := bytes.NewBufferString(`{"strategy_name": "non_existent_strat_xyz"}`)
	req = httptest.NewRequest(http.MethodPost, "/api/backtest/optimize", body)
	w = httptest.NewRecorder()
	ServeBacktestOptimize(cfg, w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400 for unknown strategy, got %d", w.Code)
	}

	var resp OptimizeResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.Status != "error" {
		t.Fatalf("expected status 'error', got '%s'", resp.Status)
	}
}
