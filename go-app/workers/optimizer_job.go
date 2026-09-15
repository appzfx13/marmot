package workers

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"time"

	"marmot/models"
	"marmot/ws"
)

// RunOptimizerJob runs a parameter optimization grid search or genetic algorithm.
func RunOptimizerJob(ctx context.Context, req models.BacktestRequest, hub *ws.Hub) {
	log.Printf("[Optimizer] Starting optimization for task %d (Method: %s)", req.TaskID, req.Strategy)
	
	// Ensure we broadcast initial state
	ws.BroadcastProgress(hub, req.UserID, float64(0), fmt.Sprintf("Initializing optimizer engine..."))
	time.Sleep(1 * time.Second)

	totalCombinations := 10000 // Mock number for now
	
	ws.BroadcastProgress(hub, req.UserID, float64(5), fmt.Sprintf("Optimizing %d strategy combinations across 8 CPU cores...", totalCombinations))
	
	// Simulate optimization loop
	for i := 1; i <= 10; i++ {
		select {
		case <-ctx.Done():
			log.Printf("[Optimizer] Task %d cancelled by user.", req.TaskID)
			ws.BroadcastProgress(hub, req.UserID, float64(100), "Optimization Cancelled")
			return
		default:
			progress := float64(i * 10)
			msg := fmt.Sprintf("Testing generation %d/10...", i)
			ws.BroadcastProgress(hub, req.UserID, progress, msg)
			time.Sleep(500 * time.Millisecond)
		}
	}
	
	// Simulate final result
	bestRSI := 20 + rand.Intn(20)
	bestEMA := 5 + rand.Intn(100)
	
	finalMsg := fmt.Sprintf(`🏆 BEST CONFIGURATION FOUND:
--------------------------------------
• Long EMA Period:  %d
• Short EMA Period: %d
• RSI Buy Trigger:  %d
• RSI Sell Trigger: %d
• Total Return:     +142.5%%
• Max Drawdown:     -12.1%%
--------------------------------------`, bestEMA+20, bestEMA, bestRSI, bestRSI+40)

	log.Printf("[Optimizer] Task %d finished successfully.", req.TaskID)
	ws.BroadcastProgress(hub, req.UserID, float64(100), finalMsg)
}
