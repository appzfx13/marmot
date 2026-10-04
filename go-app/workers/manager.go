package workers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"

	"go-app/config"
	"go-app/models"
	"go-app/services"
	"go-app/ws"
)

var (
	recentMsgMu   sync.Mutex
	recentMsgHash = make(map[string]time.Time)
)

func isDuplicateMsg(payload string) bool {
	recentMsgMu.Lock()
	defer recentMsgMu.Unlock()
	now := time.Now()
	for k, t := range recentMsgHash {
		if now.Sub(t) > 10*time.Second {
			delete(recentMsgHash, k)
		}
	}
	if t, exists := recentMsgHash[payload]; exists && now.Sub(t) < 3*time.Second {
		return true
	}
	recentMsgHash[payload] = now
	return false
}

// TaskManager handles the lifecycle of backup tasks and listens for IPC commands
type TaskManager struct {
	dbService    *services.DBService
	config       *config.Config
	hub          *ws.Hub
	redisService *services.RedisService
	activeCtx    map[string]context.CancelFunc
	mu           sync.Mutex
}

// NewTaskManager creates a new instance of TaskManager
func NewTaskManager(dbService *services.DBService, cfg *config.Config, hub *ws.Hub, redisService *services.RedisService) *TaskManager {
	return &TaskManager{
		dbService:    dbService,
		config:       cfg,
		hub:          hub,
		redisService: redisService,
		activeCtx:    make(map[string]context.CancelFunc),
	}
}

// StartListener blocks and listens for commands on both Redis Pub/Sub and persistent Redis Streams.
func (m *TaskManager) StartListener(ctx context.Context, redisService *services.RedisService, channelName string) {
	// 1. Launch persistent Redis Stream listener for guaranteed delivery and zero command loss
	go m.startStreamListener(ctx, redisService, channelName)

	// 2. Subscribe to real-time Pub/Sub for sub-millisecond execution triggers
	pubsub := redisService.Subscribe(ctx, channelName)
	defer pubsub.Close()

	log.Printf("🎧 Task Manager listening for Redis commands on channel/stream: '%s'\n", channelName)

	ch := pubsub.Channel()

	for {
		select {
		case <-ctx.Done():
			log.Println("🛑 Stopping Redis task listener...")
			return
		case msg, ok := <-ch:
			if !ok {
				return
			}
			m.handleMessage(ctx, msg.Payload)
		}
	}
}

// startStreamListener continuously polls Redis Streams with XRead blocking for durable delivery.
func (m *TaskManager) startStreamListener(ctx context.Context, redisService *services.RedisService, streamName string) {
	if redisService == nil || redisService.Client == nil {
		return
	}
	lastID := "$"
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		res, err := redisService.Client.XRead(ctx, &redis.XReadArgs{
			Streams: []string{streamName, lastID},
			Count:   10,
			Block:   2 * time.Second,
		}).Result()

		if err != nil {
			if errors.Is(err, context.Canceled) {
				return
			}
			time.Sleep(500 * time.Millisecond)
			continue
		}

		for _, stream := range res {
			for _, message := range stream.Messages {
				lastID = message.ID
				if dataStr, ok := message.Values["data"].(string); ok && dataStr != "" {
					m.handleMessage(ctx, dataStr)
				}
			}
		}
	}
}

// handleMessage parses the JSON payload and routes the command or relays progress
func (m *TaskManager) handleMessage(parentCtx context.Context, payloadStr string) {
	if isDuplicateMsg(payloadStr) {
		return
	}

	var rawAction struct {
		Action      string   `json:"action"`
		Command     string   `json:"command"`
		Date        string   `json:"date"`
		Indices     []string `json:"indices"`
		StrikeCount int      `json:"strike_count"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &rawAction); err == nil {
		action := strings.ToLower(rawAction.Action)
		if action == "" {
			action = strings.ToLower(rawAction.Command)
		}
		if action == "start_spot_1s_record" {
			ws.GetSpot1SRecorder().SetActive(true)
			return
		}
		if action == "stop_spot_1s_record" {
			ws.GetSpot1SRecorder().SetActive(false)
			return
		}
		if action == "run_daily_postmarket_merge" {
			mergeJob := NewDailyMergeJob(m.dbService, m.config, m.redisService, m.hub)
			go mergeJob.Run(parentCtx, rawAction.Date, rawAction.Indices, rawAction.StrikeCount)
			return
		}
	}

	var payload models.CommandPayload
	if err := json.Unmarshal([]byte(payloadStr), &payload); err != nil {
		log.Printf("⚠️ Invalid JSON payload received: %v\n", err)
		return
	}

	if payload.Command == "" {
		var progMsg struct {
			Type   string `json:"type"`
			TaskID string `json:"task_id"`
		}
		if err := json.Unmarshal([]byte(payloadStr), &progMsg); err == nil && progMsg.TaskID != "" {
			if progMsg.Type == "progress" || progMsg.Type == "backtest_progress" {
				if m.hub != nil {
					m.hub.BroadcastToTask(progMsg.TaskID, []byte(payloadStr))
				}
				return
			}
		}
		log.Printf("⚠️ Unknown empty command payload: %s\n", payloadStr)
		return
	}

	log.Printf("📩 Received Command: [%s] for Task ID: %s\n", payload.Command, payload.TaskID)

	switch payload.Command {
	case "START", "RESUME", "START_BACKTEST", "START_STRATEGY", "RERUN", "RESTART", "START_OPTIMIZER":
		m.startOrResumeTask(parentCtx, payload)
	case "PAUSE", "PAUSE_STRATEGY":
		m.pauseTask(payload.TaskID)
	case "CANCEL", "STOP", "STOP_STRATEGY":
		m.cancelTask(payload.TaskID)
	case "CLEAR_SESSION", "RESET_SANDBOX_STRATEGIES":
		m.clearSandboxSession(parentCtx, payload)
	default:
		log.Printf("⚠️ Unknown command: %s\n", payload.Command)
	}
}

// startOrResumeTask spins up a new BackupJob or BacktestJob Goroutine safely
func (m *TaskManager) startOrResumeTask(parentCtx context.Context, payload models.CommandPayload) {
	m.mu.Lock()
	// If this task is already running, cancel the old instance before starting a new one
	if cancel, exists := m.activeCtx[payload.TaskID]; exists {
		log.Printf("⚠️ Task #%s is already active. Restarting it...\n", payload.TaskID)
		cancel()
	}

	// Create a new cancellable context for this specific task
	taskCtx, cancel := context.WithCancel(parentCtx)
	m.activeCtx[payload.TaskID] = cancel
	m.mu.Unlock()

	// Launch the worker job in a separate Goroutine
	go m.runWorkerWrapper(taskCtx, payload)
}

// pauseTask cancels the task's context and updates DB state
func (m *TaskManager) pauseTask(taskID string) {
	m.mu.Lock()
	if cancel, exists := m.activeCtx[taskID]; exists {
		cancel()
		delete(m.activeCtx, taskID)
		log.Printf("⏸️ Task #%s context cancelled (PAUSED).\n", taskID)
	} else {
		log.Printf("⚠️ Received PAUSE for Task #%s, but it was not running locally.\n", taskID)
	}
	m.mu.Unlock()

	// Only update DB for numeric backup tasks (strategy tasks use string IDs)
	if !strings.HasPrefix(taskID, "strategy_") {
		_ = m.dbService.UpdateTaskStatus(context.Background(), taskID, "paused")
	}
}

// cancelTask cancels the task's context, cleans up map, and updates DB state
func (m *TaskManager) cancelTask(taskID string) {
	m.mu.Lock()
	if taskID == "all" || taskID == "" {
		for tid, cancel := range m.activeCtx {
			cancel()
			log.Printf("🛑 Task #%s context cancelled (CANCELLED ALL).\n", tid)
		}
		m.activeCtx = make(map[string]context.CancelFunc)
		m.mu.Unlock()
		return
	}
	if cancel, exists := m.activeCtx[taskID]; exists {
		cancel()
		delete(m.activeCtx, taskID)
		log.Printf("🛑 Task #%s context cancelled (CANCELLED).\n", taskID)
	}
	m.mu.Unlock()

	_ = m.dbService.UpdateTaskProgress(context.Background(), taskID, "cancelled", 0)
}

// runWorkerWrapper creates the job, runs it, and cleans up the active tracking map when done
func (m *TaskManager) runWorkerWrapper(ctx context.Context, payload models.CommandPayload) {
	defer func() {
		m.mu.Lock()
		delete(m.activeCtx, payload.TaskID)
		m.mu.Unlock()
	}()

	// Dispatch StrategySignalJob, BacktestJob, BackupJob, or OptimizerJob based on command / params
	if payload.Command == "START_STRATEGY" {
		job := NewStrategySignalJob(m.dbService, m.config, payload, m.hub, m.redisService)
		job.Run(ctx)
	} else if payload.Command == "START_OPTIMIZER" {
		job := NewOptimizerJob(m.dbService, m.config, payload, m.hub)
		job.Run(ctx)
	} else if payload.Command == "START_BACKTEST" || payload.Command == "RERUN" || payload.Command == "RESTART" || payload.Params.StrategyName != "" {
		job := NewBacktestJob(m.dbService, m.config, payload, m.hub)
		job.Run(ctx)
	} else {
		job := NewBackupJob(m.dbService, m.config, payload, m.hub)
		job.Run(ctx)
	}
}

// AutoResumeActiveStrategies queries active LiveStrategy records from DB on startup and resumes them
func (m *TaskManager) AutoResumeActiveStrategies(ctx context.Context) {
	if m.dbService == nil || m.dbService.Pool == nil {
		return
	}
	rows, err := m.dbService.Pool.Query(ctx, `
		SELECT id, name, strategy_name, index_name, execution_mode, user_id, allocated_capital 
		FROM trade_config_livestrategy 
		WHERE is_active = true AND is_deleted = false
	`)
	if err != nil {
		log.Printf("⚠️ [TaskManager:AutoResume] Query active strategies error: %v\n", err)
		return
	}
	defer rows.Close()

	for rows.Next() {
		var id, userID int
		var name, stratName, indexName, execMode string
		var capital float64
		if err := rows.Scan(&id, &name, &stratName, &indexName, &execMode, &userID, &capital); err == nil {
			payload := models.CommandPayload{
				TaskID:  fmt.Sprintf("strategy_%d", id),
				Command: "START_STRATEGY",
				Params: models.TaskParams{
					StrategyID:     id,
					StrategyName:   stratName,
					IndexName:      indexName,
					ExecutionMode:  execMode,
					UserID:         fmt.Sprintf("%d", userID),
					InitialCapital: capital,
				},
			}
			log.Printf("🚀 [TaskManager:AutoResume] Resuming active strategy #%d (%s) on startup\n", id, name)
			m.startOrResumeTask(ctx, payload)
		}
	}
}

// clearSandboxSession cancels active strategy worker goroutines, purges Redis telemetry, and broadcasts zeroed state.
func (m *TaskManager) clearSandboxSession(ctx context.Context, payload models.CommandPayload) {
	m.mu.Lock()
	for tid, cancel := range m.activeCtx {
		if strings.HasPrefix(tid, "strategy_") {
			cancel()
			delete(m.activeCtx, tid)
			log.Printf("🧹 [TaskManager:ClearSession] Cancelled running strategy goroutine: %s\n", tid)
		}
	}
	m.mu.Unlock()

	// 1. Purge Redis telemetry keys for sandbox and mock
	if m.redisService != nil && m.redisService.Client != nil {
		delCtx := context.Background()
		for _, pattern := range []string{"marmot:sandbox:telemetry:*", "marmot:mock:telemetry:*"} {
			keys, _ := m.redisService.Client.Keys(delCtx, pattern).Result()
			for _, k := range keys {
				_ = m.redisService.Client.Del(delCtx, k).Err()
			}
		}
	}

	// 2. Broadcast zeroed telemetry via WebSocket hub to immediately snap connected clients to 0
	if m.hub != nil {
		zeroPayload, _ := json.Marshal(map[string]interface{}{
			"type": "mock_telemetry",
			"data": map[string]interface{}{
				"live_net_pnl":           0.0,
				"realized_pnl":           0.0,
				"unrealized_pnl":         0.0,
				"open_positions_count":   0,
				"closed_positions_count": 0,
				"todays_orders_count":    0,
				"available_margin":       "100000.00",
				"cash_balance":           "100000.00",
				"margin_utilized":        "0.00",
				"positions":              []interface{}{},
				"orders":                 []interface{}{},
			},
		})
		m.hub.BroadcastToTask("all", zeroPayload)
		select {
		case m.hub.Broadcast <- zeroPayload:
		default:
		}
	}

	// 3. Restart active strategies fresh with clean state
	time.Sleep(150 * time.Millisecond)
	m.AutoResumeActiveStrategies(ctx)
}

