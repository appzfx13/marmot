package workers

import (
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"go-app/config"
	pqreader "go-app/parquet"
	"go-app/strategies"
)

// OptimizeRequest defines incoming payload for backtest hyperparameter optimization.
type OptimizeRequest struct {
	UserID            string                 `json:"user_id"`
	BackupTaskID      string                 `json:"backup_task_id"`
	StrategyName      string                 `json:"strategy_name"`
	IndexName         string                 `json:"index_name"`
	InitialCapital    float64                `json:"initial_capital"`
	StartDate         string                 `json:"start_date"`
	EndDate           string                 `json:"end_date"`
	UseVixAssist      bool                   `json:"use_vix_assist"`
	UseMacroAssist    bool                   `json:"use_macro_assist"`
	VixBackupTaskID   string                 `json:"vix_backup_task_id"`
	MacroBackupTaskID string                 `json:"macro_backup_task_id"`
	Params            map[string]interface{} `json:"params"`
}

// CandidateResult represents a tested parameter configuration with performance score.
type CandidateResult struct {
	Rank                 int     `json:"rank"`
	StopLossPoints       float64 `json:"stop_loss_points"`
	RRRatio              float64 `json:"rr_ratio"`
	EnableTrailingSL     bool    `json:"enable_trailing_sl"`
	TrailingSLTriggerR   float64 `json:"trailing_sl_trigger_r"`
	EnableRetestLayering bool    `json:"enable_retest_layering"`
	NetPnL               float64 `json:"net_pnl"`
	GrossPnL             float64 `json:"gross_pnl"`
	WinRate              float64 `json:"win_rate"`
	ProfitFactor         float64 `json:"profit_factor"`
	MaxDrawdown          float64 `json:"max_drawdown"`
	MaxDrawdownPct       float64 `json:"max_drawdown_pct"`
	SharpeRatio          float64 `json:"sharpe_ratio"`
	TotalTrades          int     `json:"total_trades"`
	WinningTrades        int     `json:"winning_trades"`
	LosingTrades         int     `json:"losing_trades"`
	ExpectancyScore      float64 `json:"expectancy_score"`
}

// OptimizeResponse is the response returned to the caller.
type OptimizeResponse struct {
	Status               string            `json:"status"`
	Message              string            `json:"message,omitempty"`
	TotalCombosEvaluated int               `json:"total_combos_evaluated"`
	DurationMs           int64             `json:"duration_ms"`
	TradingDays          int               `json:"trading_days"`
	Candidates           []CandidateResult `json:"candidates"`
}

// ExecuteOptimization performs parallel in-memory parameter evaluation across CPU cores.
func ExecuteOptimization(req OptimizeRequest, onProgress func(pct int, info string)) (*OptimizeResponse, error) {
	startTime := time.Now()

	if req.UserID == "" {
		req.UserID = "1"
	}
	if req.StrategyName == "" {
		req.StrategyName = "quant_engine"
	}
	if req.IndexName == "" {
		req.IndexName = "NIFTY"
	}
	if req.InitialCapital <= 0 {
		req.InitialCapital = 100000.0
	}

	strat, ok := strategies.GetStrategy(req.StrategyName)
	if !ok {
		return &OptimizeResponse{
			Status:  "error",
			Message: fmt.Sprintf("Strategy '%s' not registered in Go engine", req.StrategyName),
		}, fmt.Errorf("strategy not registered: %s", req.StrategyName)
	}

	if onProgress != nil {
		onProgress(5, "📂 Resolving historical Parquet dataset...")
	}

	// 1. Locate Parquet dataset
	parquetFilePath := ""
	if req.BackupTaskID != "" && req.BackupTaskID != "<nil>" {
		candBundle := fmt.Sprintf("/app/backup/%s/%s/index/dataset.parquet", req.UserID, req.BackupTaskID)
		candFlat := fmt.Sprintf("/app/backup/%s/%s/dataset.parquet", req.UserID, req.BackupTaskID)
		if isFile(candBundle) {
			parquetFilePath = candBundle
		} else if isFile(candFlat) {
			parquetFilePath = candFlat
		}
	}

	if parquetFilePath == "" {
		backupUserParent := fmt.Sprintf("/app/backup/%s", req.UserID)
		entries, scanErr := os.ReadDir(backupUserParent)
		if scanErr == nil {
			for _, entry := range entries {
				if entry.IsDir() {
					candBundle := filepath.Join(backupUserParent, entry.Name(), "index", "dataset.parquet")
					candFlat := filepath.Join(backupUserParent, entry.Name(), "dataset.parquet")
					if isFile(candBundle) {
						parquetFilePath = candBundle
						break
					} else if isFile(candFlat) {
						parquetFilePath = candFlat
						break
					}
				}
			}
		}
	}

	if parquetFilePath == "" {
		return &OptimizeResponse{
			Status:  "error",
			Message: "historical dataset.parquet not found on server",
		}, fmt.Errorf("dataset not found")
	}

	if onProgress != nil {
		onProgress(10, "⚡ Loading 1-second market ticks into RAM...")
	}

	// 2. Load Parquet ticks into memory
	candlesByDate, err := pqreader.LoadTicksByDateRange(parquetFilePath, req.StartDate, req.EndDate)
	if err != nil {
		return &OptimizeResponse{
			Status:  "error",
			Message: fmt.Sprintf("failed to read parquet dataset: %v", err),
		}, err
	}

	if len(candlesByDate) == 0 {
		return &OptimizeResponse{
			Status:  "warning",
			Message: "No trading days found in specified date range.",
		}, nil
	}

	// 3. Attach Macro Assist if requested
	if req.UseMacroAssist {
		macroPath := ""
		if req.BackupTaskID != "" {
			candBundle := fmt.Sprintf("/app/backup/%s/%s/macro/macro.parquet", req.UserID, req.BackupTaskID)
			if isFile(candBundle) {
				macroPath = candBundle
			}
		}
		if macroPath == "" {
			candSub := filepath.Join(filepath.Dir(parquetFilePath), "..", "macro", "macro.parquet")
			if isFile(candSub) {
				macroPath = candSub
			}
		}
		if macroPath != "" {
			macroHourly, macroDaily, mErr := pqreader.LoadMacroSnapshots(macroPath)
			if mErr == nil {
				for dateStr, dayTicks := range candlesByDate {
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
			}
		}
	}

	// 4. Attach India VIX Volatility if requested
	if req.UseVixAssist {
		vixPath := ""
		if req.BackupTaskID != "" {
			candBundle := fmt.Sprintf("/app/backup/%s/%s/vix/vix.parquet", req.UserID, req.BackupTaskID)
			if isFile(candBundle) {
				vixPath = candBundle
			}
		}
		if vixPath == "" {
			candSub := filepath.Join(filepath.Dir(parquetFilePath), "..", "vix", "vix.parquet")
			if isFile(candSub) {
				vixPath = candSub
			}
		}
		if vixPath != "" {
			vixMinuteMap, vixDailyMap, vErr := pqreader.LoadVixSnapshots(vixPath)
			if vErr == nil {
				for dateStr, dayTicks := range candlesByDate {
					lastVix := 0.0
					if dVix, ok := vixDailyMap[dateStr]; ok {
						lastVix = dVix
					}
					for idx := range dayTicks {
						t := &dayTicks[idx]
						curVix := 0.0
						if len(t.Datetime) >= 16 {
							minKey := strings.Replace(t.Datetime[:16], "T", " ", 1)
							if v, ok := vixMinuteMap[minKey]; ok {
								curVix = v
							}
						}
						if curVix <= 0 && lastVix > 0 {
							curVix = lastVix
						}
						if curVix > 0 {
							lastVix = curVix
							t.Vix = curVix
						}
					}
				}
			}
		}
	}

	// Collect sorted dates
	dates := make([]string, 0, len(candlesByDate))
	for d := range candlesByDate {
		dates = append(dates, d)
	}
	sort.Strings(dates)

	// 5. Generate High-Impact Combinations Matrix for Momentum Scalping & Trend Expansion
	type paramCombo struct {
		sl           float64
		rr           float64
		trailEnabled bool
		trailTrigger float64
		retest       bool
	}

	slList := []float64{5.0, 8.0, 12.0, 18.0, 25.0}
	rrList := []float64{2.0, 2.5, 3.0, 4.0}
	trailingOptions := []struct {
		enabled  bool
		triggerR float64
	}{
		{false, 1.2},
		{true, 1.2},
		{true, 1.5},
	}

	var combos []paramCombo
	for _, sl := range slList {
		for _, rr := range rrList {
			for _, trail := range trailingOptions {
				combos = append(combos, paramCombo{
					sl:           sl,
					rr:           rr,
					trailEnabled: trail.enabled,
					trailTrigger: trail.triggerR,
					retest:       false,
				})
				// For high-RR momentum scalps (SL <= 12 or RR >= 3.0), also evaluate retest layering
				if (sl <= 12.0 || rr >= 3.0) && trail.enabled && trail.triggerR == 1.2 {
					combos = append(combos, paramCombo{
						sl:           sl,
						rr:           rr,
						trailEnabled: trail.enabled,
						trailTrigger: trail.triggerR,
						retest:       true,
					})
				}
			}
		}
	}

	totalCombos := len(combos)
	numWorkers := runtime.NumCPU()
	if numWorkers > 8 {
		numWorkers = 8
	}
	if numWorkers < 2 {
		numWorkers = 2
	}

	if onProgress != nil {
		onProgress(15, fmt.Sprintf("🔬 Concurrently testing %d combinations across %d CPU cores...", totalCombos, numWorkers))
	}

	comboChan := make(chan paramCombo, totalCombos)
	resultChan := make(chan CandidateResult, totalCombos)
	for _, c := range combos {
		comboChan <- c
	}
	close(comboChan)

	var processed int64
	var wg sync.WaitGroup
	for w := 0; w < numWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for c := range comboChan {
				// Build evaluation params
				evalParams := make(map[string]interface{})
				if req.Params != nil {
					for k, v := range req.Params {
						evalParams[k] = v
					}
				}
				evalParams["stop_loss_points"] = c.sl
				evalParams["sl_pts"] = c.sl
				evalParams["rr_ratio"] = c.rr
				evalParams["enable_trailing_sl"] = c.trailEnabled
				evalParams["trailing_sl_trigger_r"] = c.trailTrigger
				evalParams["enable_retest_layering"] = c.retest

				var totalPnL, peakPnL, maxDD, totalProfit, totalLoss float64
				wins, losses := 0, 0

				for _, d := range dates {
					ticks := candlesByDate[d]
					if len(ticks) < 5 {
						continue
					}
					input := strategies.StrategyInput{
						Date:      d,
						IndexName: req.IndexName,
						Ticks:     ticks,
						Params:    evalParams,
					}
					dayResult := strat.Execute(input)
					for _, trade := range dayResult.Trades {
						totalPnL += trade.PnL
						if trade.PnL > 0 {
							totalProfit += trade.PnL
							wins++
						} else {
							totalLoss += math.Abs(trade.PnL)
							losses++
						}
						if totalPnL > peakPnL {
							peakPnL = totalPnL
						}
						dd := peakPnL - totalPnL
						if dd > maxDD {
							maxDD = dd
						}
					}
				}

				totalTrades := wins + losses
				winRate := 0.0
				if totalTrades > 0 {
					winRate = math.Round((float64(wins)/float64(totalTrades))*10000) / 100
				}
				profitFactor := 1.0
				if totalLoss > 0 {
					profitFactor = math.Round((totalProfit/totalLoss)*100) / 100
				} else if totalProfit > 0 {
					profitFactor = 5.0
				}
				maxDDPct := 0.0
				if req.InitialCapital > 0 {
					maxDDPct = math.Round((maxDD/req.InitialCapital)*10000) / 100
				}
				sharpeRatio := math.Round((totalPnL/10000.0)*100) / 100

				drawdownMultiplier := math.Max(0.1, 1.0-(maxDDPct/100.0))
				expectancy := totalPnL * drawdownMultiplier * (winRate / 100.0)
				if totalTrades < 3 {
					expectancy *= 0.5
				}

				resultChan <- CandidateResult{
					StopLossPoints:       c.sl,
					RRRatio:              c.rr,
					EnableTrailingSL:     c.trailEnabled,
					TrailingSLTriggerR:   c.trailTrigger,
					EnableRetestLayering: c.retest,
					NetPnL:               math.Round(totalPnL*100) / 100,
					GrossPnL:             math.Round(totalPnL*100) / 100,
					WinRate:              winRate,
					ProfitFactor:         profitFactor,
					MaxDrawdown:          math.Round(maxDD*100) / 100,
					MaxDrawdownPct:       maxDDPct,
					SharpeRatio:          sharpeRatio,
					TotalTrades:          totalTrades,
					WinningTrades:        wins,
					LosingTrades:         losses,
					ExpectancyScore:      math.Round(expectancy*100) / 100,
				}

				done := atomic.AddInt64(&processed, 1)
				if onProgress != nil {
					pct := int(15 + (float64(done)/float64(totalCombos))*80)
					if done%4 == 0 || done == int64(totalCombos) {
						onProgress(pct, fmt.Sprintf("Tested %d/%d combinations (SL %.1f pts, RR %.1fx)...", done, totalCombos, c.sl, c.rr))
					}
				}
			}
		}()
	}

	wg.Wait()
	close(resultChan)

	var allResults []CandidateResult
	for r := range resultChan {
		allResults = append(allResults, r)
	}

	sort.Slice(allResults, func(i, j int) bool {
		if allResults[i].ExpectancyScore != allResults[j].ExpectancyScore {
			return allResults[i].ExpectancyScore > allResults[j].ExpectancyScore
		}
		return allResults[i].NetPnL > allResults[j].NetPnL
	})

	topN := len(allResults)
	topCandidates := make([]CandidateResult, topN)
	for idx := 0; idx < topN; idx++ {
		c := allResults[idx]
		c.Rank = idx + 1
		topCandidates[idx] = c
	}

	duration := time.Since(startTime).Milliseconds()
	log.Printf("⚡ [Optimizer] Evaluated %d combinations across %d trading days in %d ms. Top winner: SL=%.1f, RR=%.1f, PnL=₹%.2f",
		totalCombos, len(dates), duration, topCandidates[0].StopLossPoints, topCandidates[0].RRRatio, topCandidates[0].NetPnL)

	return &OptimizeResponse{
		Status:               "success",
		TotalCombosEvaluated: totalCombos,
		DurationMs:           duration,
		TradingDays:          len(dates),
		Candidates:           topCandidates,
	}, nil
}

// ServeBacktestOptimize handles HTTP POST /api/backtest/optimize.
func ServeBacktestOptimize(cfg *config.Config, w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	var req OptimizeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(OptimizeResponse{
			Status:  "error",
			Message: fmt.Sprintf("invalid JSON payload: %v", err),
		})
		return
	}

	res, err := ExecuteOptimization(req, nil)
	if err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		_ = json.NewEncoder(w).Encode(res)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(res)
}
