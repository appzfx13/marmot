package workers

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strconv"
	"strings"

	"go-app/config"
	"go-app/models"
	"go-app/services"
	"go-app/ws"
)

// OptimizerJob runs asynchronous parameter optimization for BacktestTask.
type OptimizerJob struct {
	dbService *services.DBService
	config    *config.Config
	payload   models.CommandPayload
	hub       *ws.Hub
}

func NewOptimizerJob(dbService *services.DBService, cfg *config.Config, payload models.CommandPayload, hub *ws.Hub) *OptimizerJob {
	return &OptimizerJob{
		dbService: dbService,
		config:    cfg,
		payload:   payload,
		hub:       hub,
	}
}

func (j *OptimizerJob) broadcastProgress(progress float64, status string) {
	if j.hub == nil {
		return
	}
	taskID := j.payload.TaskID
	userID := j.payload.Params.UserID
	if userID == "" {
		userID = "1"
	}
	msg := map[string]interface{}{
		"type":      "optimizer_progress",
		"task_id":   taskID,
		"progress":  int(progress),
		"status":    "running",
		"step_info": status,
	}
	data, _ := json.Marshal(msg)
	j.hub.BroadcastToTask(taskID, data)
	j.hub.BroadcastToTask(userID, data)
}

func (j *OptimizerJob) broadcastComplete(taskID string, winner CandidateResult, candidates []CandidateResult) {
	if j.hub == nil {
		return
	}
	userID := j.payload.Params.UserID
	if userID == "" {
		userID = "1"
	}
	msg := map[string]interface{}{
		"type":       "optimizer_completed",
		"task_id":    taskID,
		"progress":   100,
		"status":     "completed",
		"winner":     winner,
		"candidates": candidates,
		"step_info":  fmt.Sprintf("🏆 Winner: SL %.1f pts, RR %.1fx (Net PnL: ₹%.2f)", winner.StopLossPoints, winner.RRRatio, winner.NetPnL),
	}
	data, _ := json.Marshal(msg)
	j.hub.BroadcastToTask(taskID, data)
	j.hub.BroadcastToTask(userID, data)
}

// Run executes the asynchronous parameter optimization for a BacktestTask.
func (j *OptimizerJob) Run(ctx context.Context) {
	params := j.payload.Params
	taskID := j.payload.TaskID
	userID := params.UserID
	if userID == "" {
		userID = "1"
	}

	log.Printf("🔬 [Optimizer #%s] Starting async hyperparameter optimization for Backtest #%s...", taskID, taskID)
	j.broadcastProgress(5, "🚀 Starting Go in-memory parallel parameter optimizer...")

	// Resolve parameters
	req := OptimizeRequest{
		UserID:            userID,
		BackupTaskID:      params.BackupTaskID,
		StrategyName:      params.StrategyName,
		IndexName:         params.IndexName,
		InitialCapital:    params.InitialCapital,
		StartDate:         params.StartDate,
		EndDate:           params.EndDate,
		Params:            params.Params,
	}

	if val, ok := params.Params["use_vix_assist"]; ok {
		switch v := val.(type) {
		case bool:
			req.UseVixAssist = v
		case string:
			req.UseVixAssist = strings.EqualFold(v, "true") || v == "1" || strings.EqualFold(v, "on")
		}
	}
	if val, ok := params.Params["use_macro_assist"]; ok {
		switch v := val.(type) {
		case bool:
			req.UseMacroAssist = v
		case string:
			req.UseMacroAssist = strings.EqualFold(v, "true") || v == "1" || strings.EqualFold(v, "on")
		}
	}

	res, err := ExecuteOptimization(req, func(pct int, info string) {
		j.broadcastProgress(float64(pct), info)
	})

	if err != nil || res == nil || len(res.Candidates) == 0 {
		errMsg := "optimization failed to produce candidate results"
		if err != nil {
			errMsg = err.Error()
		}
		log.Printf("❌ [Optimizer #%s] Error: %s", taskID, errMsg)
		j.broadcastProgress(100, "❌ "+errMsg)
		if j.dbService != nil && j.dbService.Pool != nil {
			btID, parseErr := strconv.Atoi(taskID)
			if parseErr == nil && btID > 0 {
				_, _ = j.dbService.Pool.Exec(ctx, `
					UPDATE backtest_backtesttask 
					SET parameters = jsonb_set(COALESCE(parameters, '{}'::jsonb), '{optimizer_status}', '"error"'::jsonb)
					WHERE id = $1
				`, btID)
			}
		}
		return
	}

	winner := res.Candidates[0]

	// Save optimal config results into BacktestTask.parameters in PostgreSQL
	if j.dbService != nil && j.dbService.Pool != nil {
		btID, parseErr := strconv.Atoi(taskID)
		if parseErr == nil && btID > 0 {
			optResultsJSON, _ := json.Marshal(map[string]interface{}{
				"status":                 "completed",
				"total_combos_evaluated": res.TotalCombosEvaluated,
				"duration_ms":            res.DurationMs,
				"trading_days":           res.TradingDays,
				"winner":                 winner,
				"candidates":             res.Candidates,
			})

			_, dbErr := j.dbService.Pool.Exec(ctx, `
				UPDATE backtest_backtesttask 
				SET parameters = jsonb_set(
					jsonb_set(COALESCE(parameters, '{}'::jsonb), '{optimizer_results}', $1::jsonb),
					'{optimizer_status}', '"completed"'::jsonb
				)
				WHERE id = $2
			`, string(optResultsJSON), btID)

			if dbErr != nil {
				log.Printf("⚠️ [Optimizer #%s] Failed to save optimizer results to PostgreSQL: %v", taskID, dbErr)
			} else {
				log.Printf("💾 [Optimizer #%s] Successfully saved optimizer results to PostgreSQL BacktestTask #%d", taskID, btID)
			}
		}
	}

	j.broadcastComplete(taskID, winner, res.Candidates)
	log.Printf("✅ [Optimizer #%s] Completed successfully in %d ms! Winner: SL=%.1f, RR=%.1f, NetPnL=₹%.2f",
		taskID, res.DurationMs, winner.StopLossPoints, winner.RRRatio, winner.NetPnL)
}
