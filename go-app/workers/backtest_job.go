package workers

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go-app/config"
	"go-app/models"
	pqreader "go-app/parquet"
	"go-app/services"
	"go-app/strategies"
	"go-app/ws"
)

// BacktestJob handles parallel backtest execution over date-partitioned Parquet datasets.
type BacktestJob struct {
	dbService *services.DBService
	config    *config.Config
	payload   models.CommandPayload
	hub       *ws.Hub
}

// NewBacktestJob creates a new BacktestJob instance.
func NewBacktestJob(dbService *services.DBService, cfg *config.Config, payload models.CommandPayload, hub *ws.Hub) *BacktestJob {
	return &BacktestJob{
		dbService: dbService,
		config:    cfg,
		payload:   payload,
		hub:       hub,
	}
}

func (j *BacktestJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	params := j.payload.Params

	strategyName := params.StrategyName
	startDate := params.StartDate
	endDate := params.EndDate
	indexName := params.IndexName
	userID := params.UserID

	if userID == "" || userID == "<nil>" {
		userID = "1"
	}
	if strategyName == "" || strategyName == "<nil>" {
		strategyName = "quant_engine"
	}

	strat, ok := strategies.GetStrategy(strategyName)
	if !ok {
		errStr := fmt.Sprintf("Strategy '%s' not found in Go registry", strategyName)
		log.Printf("❌ [Backtest #%s] %s\n", taskID, errStr)
		_ = j.recordBacktestError(ctx, taskID, errStr)
		return
	}

	log.Printf("🚀 [Backtest #%s] Executing '%s' for User #%s, Index %s from %s to %s\n",
		taskID, strat.GetName(), userID, indexName, startDate, endDate)

	_ = j.updateBacktestProgress(ctx, taskID, "running", 5)
	j.broadcastBacktestProgress(ctx, taskID, 5, "running", 0, 0)

	start, err := time.Parse("2006-01-02", startDate)
	if err != nil {
		_ = j.recordBacktestError(ctx, taskID, fmt.Sprintf("invalid start date: %v", err))
		return
	}
	end, err := time.Parse("2006-01-02", endDate)
	if err != nil {
		_ = j.recordBacktestError(ctx, taskID, fmt.Sprintf("invalid end date: %v", err))
		return
	}

	totalDays := int(end.Sub(start).Hours()/24) + 1
	if totalDays <= 0 {
		totalDays = 1
	}

	backupTaskID := params.BackupTaskID
	_ = strings.ToLower(indexName) // idxLower reserved for future partitioned datasets

	// Resolve flat parquet dataset path: /app/backup/{userID}/{backupTaskID}/dataset.parquet
	parquetFilePath := ""
	if backupTaskID != "" && backupTaskID != "<nil>" {
		candidate := fmt.Sprintf("/app/backup/%s/%s/dataset.parquet", userID, backupTaskID)
		if isFile(candidate) {
			parquetFilePath = candidate
		}
	}

	// Fallback: scan /app/backup/{userID}/ for first backup task dir containing dataset.parquet
	if parquetFilePath == "" {
		backupUserParent := fmt.Sprintf("/app/backup/%s", userID)
		entries, scanErr := os.ReadDir(backupUserParent)
		if scanErr == nil {
			for _, entry := range entries {
				if entry.IsDir() {
					candidate := filepath.Join(backupUserParent, entry.Name(), "dataset.parquet")
					if isFile(candidate) {
						parquetFilePath = candidate
						log.Printf("📂 [Backtest #%s] No backupTaskID, using first found: %s\n", taskID, parquetFilePath)
						break
					}
				}
			}
		}
	}

	// Preload all ticks from parquet once; group by date for O(1) per-day lookup
	candlesByDate := make(map[string][]strategies.MarketTick)
	if parquetFilePath != "" {
		loaded, pqErr := pqreader.LoadTicksByDate(parquetFilePath)
		if pqErr != nil {
			log.Printf("⚠️  [Backtest #%s] Parquet load failed (%v), will use synthetic ticks\n", taskID, pqErr)
		} else {
			candlesByDate = loaded
			log.Printf("✅ [Backtest #%s] Parquet loaded: %d trading days from %s\n", taskID, len(candlesByDate), parquetFilePath)
		}
	} else {
		log.Printf("⚠️  [Backtest #%s] No dataset.parquet found, will use synthetic ticks\n", taskID)
	}

	// ── AI Macro Assist Loading ───────────────────────────────────────────────
	useMacroAssist := false
	if val, ok := params.Params["use_macro_assist"]; ok {
		switch v := val.(type) {
		case bool:
			useMacroAssist = v
		case string:
			useMacroAssist = strings.EqualFold(v, "true") || v == "1" || strings.EqualFold(v, "on")
		}
	}

	var macroHourly map[string]strategies.MacroSnapshot
	var macroDaily map[string]strategies.MacroSnapshot
	if useMacroAssist {
		macroPath := ""
		// 1. Check directory of current dataset.parquet for macro_1h_{INDEX}.parquet
		if parquetFilePath != "" {
			cand := filepath.Join(filepath.Dir(parquetFilePath), fmt.Sprintf("macro_1h_%s.parquet", indexName))
			if isFile(cand) {
				macroPath = cand
			}
		}
		// 2. Fallback: scan /app/backup/{userID}/ for any macro_1h_{INDEX}.parquet or macro backup
		if macroPath == "" {
			userBackupDir := fmt.Sprintf("/app/backup/%s", userID)
			entries, _ := os.ReadDir(userBackupDir)
			for _, e := range entries {
				if e.IsDir() {
					cand1 := filepath.Join(userBackupDir, e.Name(), fmt.Sprintf("macro_1h_%s.parquet", indexName))
					if isFile(cand1) {
						macroPath = cand1
						break
					}
					cand2 := filepath.Join(userBackupDir, e.Name(), "macro_1h_NIFTY.parquet")
					if isFile(cand2) {
						macroPath = cand2
						break
					}
				}
			}
		}

		if macroPath != "" {
			hMap, dMap, mErr := pqreader.LoadMacroSnapshots(macroPath)
			if mErr != nil {
				log.Printf("⚠️  [Backtest #%s] AI Macro load failed (%v)\n", taskID, mErr)
			} else {
				macroHourly = hMap
				macroDaily = dMap
				log.Printf("🧠 [Backtest #%s] AI Macro Assist ENABLED: %d hourly snapshots from %s\n", taskID, len(macroHourly), macroPath)
			}
		} else {
			log.Printf("ℹ️  [Backtest #%s] AI Macro Assist enabled but no macro parquet file found\n", taskID)
		}
	}

	compounding := NewCompoundingEngine(params.InitialCapital, params.Params)
	allTrades := make([]strategies.TradeSignal, 0)
	var totalPnL, peakPnL, maxDD, totalProfit, totalLoss float64
	var totalUtilizedCapital, maxUtilizedCapital float64
	winningTrades, losingTrades := 0, 0

	processedDays := 0
	currDate := start

	for !currDate.After(end) {
		select {
		case <-ctx.Done():
			log.Printf("⏸️ [Backtest #%s] Execution cancelled by user.\n", taskID)
			return
		default:
		}

		dateStr := currDate.Format("2006-01-02")

		// Retrieve pre-loaded real ticks for this date. Skip if data is absent.
		dayTicks, hasReal := candlesByDate[dateStr]
		if !hasReal || len(dayTicks) == 0 {
			log.Printf("⚠️ [Backtest #%s] Missing Parquet data for date %s. Skipping day.", taskID, dateStr)
			currDate = currDate.AddDate(0, 0, 1)
			continue
		}

		// Attach AI Macro Snapshot to each tick if enabled
		if useMacroAssist && (len(macroHourly) > 0 || len(macroDaily) > 0) {
			for idx := range dayTicks {
				t := &dayTicks[idx]
				var snap *strategies.MacroSnapshot
				if len(t.Datetime) >= 13 {
					hourKey := strings.Replace(t.Datetime[:13], "T", " ", 1)
					if s, ok := macroHourly[hourKey]; ok {
						snap = &s
					}
				}
				if snap == nil && len(macroDaily) > 0 {
					if s, ok := macroDaily[dateStr]; ok {
						snap = &s
					}
				}
				t.Macro = snap
			}
		}

		input := strategies.StrategyInput{
			Date:      dateStr,
			IndexName: indexName,
			Ticks:     dayTicks,
			Params:    params.Params,
		}

		dayResult := strat.Execute(input)

		for _, trade := range dayResult.Trades {
			if compounding.EnableAICompounding && compounding.Profile != CompoundingFixed {
				lotCount := compounding.CalculateLotSize(trade.EntryPrice)
				baseLot := compounding.BaseLots
				if baseLot <= 0 {
					baseLot = 1
				}
				if lotCount != baseLot && baseLot > 0 {
					multiplier := float64(lotCount) / float64(baseLot)
					trade.Quantity = int(float64(trade.Quantity) * multiplier)
					trade.PnL = math.Round(trade.PnL*multiplier*100) / 100
					trade.UtilizedCapital = math.Round(trade.EntryPrice * float64(trade.Quantity))
				}
			}

			compounding.UpdatePnL(trade.PnL)
			allTrades = append(allTrades, trade)
			totalPnL += trade.PnL
			totalUtilizedCapital += trade.UtilizedCapital
			if trade.UtilizedCapital > maxUtilizedCapital {
				maxUtilizedCapital = trade.UtilizedCapital
			}
			if trade.PnL > 0 {
				winningTrades++
				totalProfit += trade.PnL
			} else if trade.PnL < 0 {
				losingTrades++
				totalLoss += math.Abs(trade.PnL)
			}

			if totalPnL > peakPnL {
				peakPnL = totalPnL
			}
			dd := peakPnL - totalPnL
			if dd > maxDD {
				maxDD = dd
			}
		}

		processedDays++
		progress := 5 + int((float64(processedDays)/float64(totalDays))*90)
		if progress > 95 {
			progress = 95
		}

		_ = j.updateBacktestProgress(ctx, taskID, "running", progress)
		j.broadcastBacktestProgress(ctx, taskID, progress, "running", totalPnL, len(allTrades))

		currDate = currDate.AddDate(0, 0, 1)
	}

	// Calculate Final Summary Metrics
	totalTrades := len(allTrades)
	winRate := 0.0
	if totalTrades > 0 {
		winRate = math.Round((float64(winningTrades)/float64(totalTrades)*100.0)*100) / 100
	}
	profitFactor := 99.99
	if totalLoss > 0 {
		profitFactor = math.Round((totalProfit/totalLoss)*100) / 100
	}

	sharpeRatio := math.Round((totalPnL/10000.0)*100) / 100

	avgUtilizedCapital := 0.0
	if totalTrades > 0 {
		avgUtilizedCapital = math.Round(totalUtilizedCapital/float64(totalTrades)*100) / 100
	}
	capUtilizationPct := 0.0
	if params.InitialCapital > 0 {
		capUtilizationPct = math.Round((maxUtilizedCapital/params.InitialCapital)*10000) / 100
	}
	roiOnUtilized := 0.0
	if maxUtilizedCapital > 0 {
		roiOnUtilized = math.Round((totalPnL/maxUtilizedCapital)*10000) / 100
	}

	metrics := map[string]interface{}{
		"net_pnl":                 math.Round(totalPnL*100) / 100,
		"win_rate":                winRate,
		"total_trades":            totalTrades,
		"winning_trades":          winningTrades,
		"losing_trades":           losingTrades,
		"max_drawdown":            math.Round(maxDD*100) / 100,
		"profit_factor":           profitFactor,
		"sharpe_ratio":            sharpeRatio,
		"max_utilized_capital":    maxUtilizedCapital,
		"avg_utilized_capital":    avgUtilizedCapital,
		"capital_utilization_pct": capUtilizationPct,
		"roi_on_utilized":         roiOnUtilized,
		"final_capital":           math.Round(compounding.CurrentCapital*100) / 100,
		"compounding_profile":     string(compounding.Profile),
		"risk_profile":            string(compounding.RiskProfile),
	}

	// Write Detailed Trade Log JSON Result File
	backtestOutputDir := fmt.Sprintf("/app/data/users/%s/backtests", userID)
	_ = os.MkdirAll(backtestOutputDir, 0755)
	resultFilePath := filepath.Join(backtestOutputDir, fmt.Sprintf("backtest_%s.json", taskID))

	resultFile, err := os.Create(resultFilePath)
	if err == nil {
		for _, trade := range allTrades {
			b, _ := json.Marshal(trade)
			_, _ = resultFile.Write(b)
			_, _ = resultFile.WriteString("\n")
		}
		resultFile.Close()
	}

	// Update PostgreSQL with JSONB metrics & completion
	if err := j.markBacktestComplete(ctx, taskID, resultFilePath, metrics); err != nil {
		log.Printf("❌ [Backtest #%s] Failed to update PostgreSQL: %v\n", taskID, err)
		_ = j.recordBacktestError(ctx, taskID, fmt.Sprintf("DB complete update error: %v", err))
		return
	}

	log.Printf("✅ [Backtest #%s] Complete! Net PnL: ₹%.2f, Win Rate: %.1f%%, Total Trades: %d\n",
		taskID, totalPnL, winRate, totalTrades)
	j.broadcastBacktestProgress(ctx, taskID, 100, "completed", totalPnL, totalTrades)
}

func (j *BacktestJob) updateBacktestProgress(ctx context.Context, taskID string, status string, progress int) error {
	_, err := j.dbService.Pool.Exec(ctx, `UPDATE backtest_backtesttask SET status = $1, progress = $2, updated_at = $3 WHERE id = $4`, status, progress, time.Now(), taskID)
	return err
}

func (j *BacktestJob) markBacktestComplete(ctx context.Context, taskID string, filePath string, metrics map[string]interface{}) error {
	metricsJSON, _ := json.Marshal(metrics)
	_, err := j.dbService.Pool.Exec(ctx, `
		UPDATE backtest_backtesttask 
		SET status = 'completed', progress = 100, result_file_path = $1, metrics = $2, updated_at = $3 
		WHERE id = $4
	`, filePath, string(metricsJSON), time.Now(), taskID)
	return err
}

func (j *BacktestJob) recordBacktestError(ctx context.Context, taskID string, errorMsg string) error {
	_, err := j.dbService.Pool.Exec(ctx, `
		UPDATE backtest_backtesttask 
		SET status = 'error', result_file_path = NULL, error_logs = COALESCE(error_logs || E'\n', '') || $1, updated_at = $2 
		WHERE id = $3
	`, errorMsg, time.Now(), taskID)
	j.broadcastBacktestProgress(ctx, taskID, 0, "error", 0, 0)
	return err
}

func (j *BacktestJob) broadcastBacktestProgress(ctx context.Context, taskID string, progress int, status string, pnl float64, totalTrades int) {
	if j.hub == nil {
		return
	}
	msg := map[string]interface{}{
		"type":         "backtest_progress",
		"task_id":      taskID,
		"progress":     progress,
		"status":       status,
		"net_pnl":      pnl,
		"total_trades": totalTrades,
	}
	data, _ := json.Marshal(msg)
	j.hub.BroadcastToTask(taskID, data)
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return info.IsDir()
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return !info.IsDir()
}
