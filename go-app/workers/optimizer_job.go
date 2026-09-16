package workers

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"sync"
	"sync/atomic"

	"go-app/config"
	"go-app/models"
	pqreader "go-app/parquet"
	"go-app/services"
	"go-app/strategies"
	"go-app/ws"
)

// OptimizerJob runs a real concurrent grid search over EMA/RSI parameter space.
type OptimizerJob struct {
	dbService *services.DBService
	config    *config.Config
	payload   models.CommandPayload
	hub       *ws.Hub
}

// OptimizerResult holds the result for one parameter combination.
type OptimizerResult struct {
	EmaFast    int
	EmaSlow    int
	RsiBuy     int
	RsiSell    int
	RRRatio    float64
	TotalPnL   float64
	WinRate    float64
	MaxDD      float64
	TotalTrades int
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
	userID := j.payload.Params.UserID
	if userID == "" {
		userID = "1"
	}
	msg := map[string]interface{}{
		"type":     "progress",
		"task_id":  userID,
		"progress": int(progress),
		"status":   status,
	}
	data, _ := json.Marshal(msg)
	j.hub.BroadcastToTask(userID, data)
}

// Run executes a real parallel grid search over EMA/RSI parameter ranges.
func (j *OptimizerJob) Run(ctx context.Context) {
	params := j.payload.Params
	userID := params.UserID
	if userID == "" {
		userID = "1"
	}

	// ── 1. Resolve RSI / EMA search bounds ────────────────────────────────────
	rsiMin := params.RsiMin
	rsiMax := params.RsiMax
	emaMin := params.EmaMin
	emaMax := params.EmaMax
	targetMetric := params.TargetMetric
	if targetMetric == "" {
		targetMetric = "total_profit"
	}
	if rsiMin <= 0 { rsiMin = 10 }
	if rsiMax <= 0 || rsiMax <= rsiMin { rsiMax = rsiMin + 30 }
	if emaMin <= 0 { emaMin = 5 }
	if emaMax <= 0 || emaMax <= emaMin { emaMax = emaMin + 50 }
	if emaMax > 100 { emaMax = 100 } // Hard cap EMA for intraday sanity

	log.Printf("🔬 [Optimizer #%s] Grid: EMA [%d–%d], RSI [%d–%d], Metric: %s",
		j.payload.TaskID, emaMin, emaMax, rsiMin, rsiMax, targetMetric)

	// ── 2. Load parquet dataset ────────────────────────────────────────────────
	j.broadcastProgress(2, "📂 Loading historical dataset from disk...")

	backupTaskID := params.BackupTaskID
	parquetFilePath := ""
	if backupTaskID != "" {
		candidate := fmt.Sprintf("/app/backup/%s/%s/dataset.parquet", userID, backupTaskID)
		if _, err := os.Stat(candidate); err == nil {
			parquetFilePath = candidate
		}
	}
	if parquetFilePath == "" {
		backupUserParent := fmt.Sprintf("/app/backup/%s", userID)
		entries, err := os.ReadDir(backupUserParent)
		if err == nil {
			for _, entry := range entries {
				if entry.IsDir() {
					candidate := filepath.Join(backupUserParent, entry.Name(), "dataset.parquet")
					if _, statErr := os.Stat(candidate); statErr == nil {
						parquetFilePath = candidate
						break
					}
				}
			}
		}
	}

	if parquetFilePath == "" {
		j.broadcastProgress(100, "❌ No parquet dataset found. Please run a backup task first.")
		log.Printf("❌ [Optimizer #%s] No dataset.parquet found for user %s", j.payload.TaskID, userID)
		return
	}

	candlesByDate, pqErr := pqreader.LoadTicksByDate(parquetFilePath)
	if pqErr != nil {
		j.broadcastProgress(100, fmt.Sprintf("❌ Parquet load error: %v", pqErr))
		log.Printf("❌ [Optimizer #%s] Parquet error: %v", j.payload.TaskID, pqErr)
		return
	}
	tradingDays := len(candlesByDate)
	log.Printf("✅ [Optimizer #%s] Loaded %d trading days from %s", j.payload.TaskID, tradingDays, parquetFilePath)
	j.broadcastProgress(5, fmt.Sprintf("✅ Loaded %d trading days of historical data.", tradingDays))

	// ── 3. Collect sorted dates ────────────────────────────────────────────────
	dates := make([]string, 0, tradingDays)
	for d := range candlesByDate {
		dates = append(dates, d)
	}
	sort.Strings(dates)

	// ── 4. Generate grid of combinations ──────────────────────────────────────
	type combo struct {
		emaFast int
		emaSlow int
		rsiBuy  int
		rsiSell int
		rrRatio float64
	}
	var combos []combo
	for emaF := emaMin; emaF <= emaMax; emaF += 10 {
		for emaS := emaF + 10; emaS <= emaMax; emaS += 15 {
			for rsiB := rsiMin; rsiB <= rsiMax; rsiB += 10 {
				for rsiSell := rsiB + 20; rsiSell <= 90; rsiSell += 10 {
					for rr := 1.5; rr <= 3.5; rr += 1.0 {
						combos = append(combos, combo{emaF, emaS, rsiB, rsiSell, rr})
					}
				}
			}
		}
	}
	totalCombos := len(combos)
	if totalCombos == 0 {
		j.broadcastProgress(100, "❌ No valid parameter combinations in the given ranges.")
		return
	}

	numWorkers := runtime.NumCPU()
	if numWorkers > 8 {
		numWorkers = 8
	}
	log.Printf("🔧 [Optimizer #%s] %d combinations across %d CPU cores", j.payload.TaskID, totalCombos, numWorkers)
	j.broadcastProgress(8, fmt.Sprintf("🔧 Optimizing %d combinations across %d CPU cores...", totalCombos, numWorkers))

	// ── 5. Concurrent grid search ─────────────────────────────────────────────
	comboChan := make(chan combo, totalCombos)
	resultChan := make(chan OptimizerResult, totalCombos)
	var processed int64

	for _, c := range combos {
		comboChan <- c
	}
	close(comboChan)

	var wg sync.WaitGroup
	for w := 0; w < numWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for c := range comboChan {
				select {
				case <-ctx.Done():
					return
				default:
				}

				strat := strategies.NewQuantEngineStrategy("optimizer")
				overrideParams := map[string]interface{}{
					"ema_fast": c.emaFast,
					"ema_slow": c.emaSlow,
					"rsi_buy":  c.rsiBuy,
					"rsi_sell": c.rsiSell,
					"rr_ratio": c.rrRatio,
				}

				var totalPnL, peakPnL, maxDD, totalProfit, totalLoss float64
				wins, losses := 0, 0

				for _, date := range dates {
					ticks, ok := candlesByDate[date]
					if !ok || len(ticks) < 5 {
						continue
					}
					input := strategies.StrategyInput{
						Date:      date,
						IndexName: ticks[0].IndexName,
						Ticks:     ticks,
						Params:    overrideParams,
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

				winRate := 0.0
				if wins+losses > 0 {
					winRate = float64(wins) / float64(wins+losses) * 100
				}

				if wins+losses >= 5 && winRate >= 20.0 {
					resultChan <- OptimizerResult{
						EmaFast:     c.emaFast,
						EmaSlow:     c.emaSlow,
						RsiBuy:      c.rsiBuy,
						RsiSell:     c.rsiSell,
						RRRatio:     c.rrRatio,
						TotalPnL:    totalPnL,
						WinRate:     winRate,
						MaxDD:       maxDD,
						TotalTrades: wins + losses,
					}
				}

				done := atomic.AddInt64(&processed, 1)
				pct := float64(done) / float64(totalCombos) * 85
				if done%50 == 0 || done == int64(totalCombos) {
					j.broadcastProgress(8+pct,
						fmt.Sprintf("⚙️  Tested %d / %d combinations (EMA %d/%d, RSI %d/%d)...",
							done, totalCombos, c.emaFast, c.emaSlow, c.rsiBuy, c.rsiSell))
				}
			}
		}()
	}

	wg.Wait()
	close(resultChan)

	select {
	case <-ctx.Done():
		j.broadcastProgress(100, "⚠️  Optimization cancelled by user.")
		return
	default:
	}

	// ── 6. Aggregate & rank results ────────────────────────────────────────────
	j.broadcastProgress(95, "📊 Ranking results and finding best configuration...")

	var allResults []OptimizerResult
	for r := range resultChan {
		allResults = append(allResults, r)
	}

	if len(allResults) == 0 {
		j.broadcastProgress(100, "⚠️  No results produced. Dataset may be too small.")
		return
	}

	sort.Slice(allResults, func(i, k int) bool {
		switch targetMetric {
		case "win_rate":
			return allResults[i].WinRate > allResults[k].WinRate
		case "min_drawdown":
			return allResults[i].MaxDD < allResults[k].MaxDD
		default: // total_profit
			return allResults[i].TotalPnL > allResults[k].TotalPnL
		}
	})

	best := allResults[0]

	// ── 7. Emit top-5 results + winner summary ─────────────────────────────────
	top := allResults
	if len(top) > 5 {
		top = top[:5]
	}
	for rank, r := range top {
		j.broadcastProgress(95, fmt.Sprintf(
			"🏅 Rank #%d → EMA %d/%d | RSI %d/%d | RR %.1f | PnL: ₹%.0f | WinRate: %.1f%% | MaxDD: ₹%.0f | Trades: %d",
			rank+1, r.EmaFast, r.EmaSlow, r.RsiBuy, r.RsiSell, r.RRRatio, r.TotalPnL, r.WinRate, r.MaxDD, r.TotalTrades))
	}

	finalMsg := fmt.Sprintf(
		"🏆 BEST CONFIGURATION FOUND:\n──────────────────────────────────────────\n"+
			"• EMA Fast Period :  %d\n"+
			"• EMA Slow Period :  %d\n"+
			"• RSI Buy Trigger :  %d\n"+
			"• RSI Sell Trigger:  %d\n"+
			"• Risk:Reward     :  %.1f\n"+
			"• Net PnL         :  ₹%.2f\n"+
			"• Win Rate        :  %.1f%%\n"+
			"• Max Drawdown    :  ₹%.2f\n"+
			"• Total Trades    :  %d\n"+
			"──────────────────────────────────────────\n"+
			"(%d combinations tested | Metric: %s)",
		best.EmaFast, best.EmaSlow, best.RsiBuy, best.RsiSell, best.RRRatio,
		best.TotalPnL, best.WinRate, best.MaxDD, best.TotalTrades,
		totalCombos, targetMetric,
	)

	log.Printf("✅ [Optimizer #%s] Done. Best PnL=%.2f, EMA=%d/%d", j.payload.TaskID, best.TotalPnL, best.EmaFast, best.EmaSlow)
	j.broadcastProgress(100, finalMsg)
}
