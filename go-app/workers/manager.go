package workers

import (
	"context"
	"encoding/json"
	"log"
	"sync"

	"go-app/config"
	"go-app/models"
	"go-app/services"
	"go-app/ws"
)

// TaskManager handles the lifecycle of backup tasks and listens for IPC commands
type TaskManager struct {
	dbService *services.DBService
	config    *config.Config
	hub       *ws.Hub
	activeCtx map[string]context.CancelFunc
	mu        sync.Mutex
}

// NewTaskManager creates a new instance of TaskManager
func NewTaskManager(dbService *services.DBService, cfg *config.Config, hub *ws.Hub) *TaskManager {
	return &TaskManager{
		dbService: dbService,
		config:    cfg,
		hub:       hub,
		activeCtx: make(map[string]context.CancelFunc),
	}
}

// StartListener blocks and listens for commands on the given Redis Pub/Sub channel
func (m *TaskManager) StartListener(ctx context.Context, redisService *services.RedisService, channelName string) {
	pubsub := redisService.Subscribe(ctx, channelName)
	defer pubsub.Close()

	log.Printf("🎧 Task Manager listening for Redis commands on channel: '%s'\n", channelName)

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

// handleMessage parses the JSON payload and routes the command or relays progress
func (m *TaskManager) handleMessage(parentCtx context.Context, payloadStr string) {
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
	case "START", "RESUME", "START_BACKTEST":
		m.startOrResumeTask(parentCtx, payload)
	case "PAUSE":
		m.pauseTask(payload.TaskID)
	case "CANCEL", "STOP":
		m.cancelTask(payload.TaskID)
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

	_ = m.dbService.UpdateTaskStatus(context.Background(), taskID, "paused") 
}

// cancelTask cancels the task's context, cleans up map, and updates DB state
func (m *TaskManager) cancelTask(taskID string) {
	m.mu.Lock()
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

	// Dispatch BacktestJob or BackupJob based on command / params
	if payload.Command == "START_BACKTEST" || payload.Params.StrategyName != "" {
		job := NewBacktestJob(m.dbService, m.config, payload, m.hub)
		job.Run(ctx)
	} else {
		job := NewBackupJob(m.dbService, m.config, payload, m.hub)
		job.Run(ctx)
	}
}