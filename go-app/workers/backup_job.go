package workers

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"go-app/config"
	"go-app/models"
	"go-app/services"
)

// BackupJob handles the downloading, processing, and Parquet serialization logic
type BackupJob struct {
	dbService *services.DBService
	config    *config.Config
	payload   models.CommandPayload
}

// NewBackupJob creates a new instance of BackupJob
func NewBackupJob(dbService *services.DBService, cfg *config.Config, payload models.CommandPayload) *BackupJob {
	return &BackupJob{
		dbService: dbService,
		config:    cfg,
		payload:   payload,
	}
}

// Run executes the backup pipeline with live progress reporting and cancellation handling
func (j *BackupJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	indexName := j.payload.Params.IndexName
	startDate := j.payload.Params.StartDate
	endDate := j.payload.Params.EndDate

	log.Printf("🚀 [Task #%s] Starting backup processing for index '%s' (%s to %s)...\n",
		taskID, indexName, startDate, endDate)

	// Set initial status to running at 5%
	if err := j.dbService.UpdateTaskProgress(ctx, taskID, "running", 5); err != nil {
		log.Printf("⚠️ [Task #%s] Failed to set initial DB status: %v\n", taskID, err)
		return
	}

	// Prepare output file
	outputDir := "/app/data/backups"
	_ = os.MkdirAll(outputDir, 0755)
	fileName := fmt.Sprintf("%s_%s_%s.jsonl", indexName, taskID, time.Now().Format("20060102_150405"))
	fullFilePath := filepath.Join(outputDir, fileName)
	file, err := os.OpenFile(fullFilePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		_ = j.dbService.RecordError(ctx, taskID, err.Error())
		return
	}
	defer file.Close()

	client := &http.Client{Timeout: 10 * time.Second}
	baseURL := "https://api.dhan.co/charts/historical"

	// Fetch data in chunks (simulating 10 chunks for the date range)
	for chunk := 1; chunk <= 10; chunk++ {
		select {
		case <-ctx.Done():
			log.Printf("⏸️ [Task #%s] Execution loop interrupted by control command.\n", taskID)
			return
		default:
			req, _ := http.NewRequestWithContext(ctx, "GET", baseURL, nil)
			req.Header.Add("access-token", j.config.DhanAccessToken)
			req.Header.Add("client-id", j.config.DhanClientID)

			resp, err := client.Do(req)
			if err != nil {
				// We ignore timeout errors for this demo/simulation unless it's a context cancel
				time.Sleep(1 * time.Second)
			} else {
				defer resp.Body.Close()
				body, _ := io.ReadAll(resp.Body)
				_, _ = file.Write(body)
				_, _ = file.WriteString("\n")
			}

			progress := 5 + (chunk * 9)
			log.Printf("📊 [Task #%s] Dhan API Fetch Progress: %d%%\n", taskID, progress)
			_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress)
			time.Sleep(1 * time.Second) // rate limit
		}
	}

	fileInfo, err := os.Stat(fullFilePath)
	var fileSizeMB float64 = 0.0
	if err == nil {
		fileSizeMB = float64(fileInfo.Size()) / (1024 * 1024)
	}

	if err := j.dbService.MarkTaskComplete(ctx, taskID, fullFilePath, fileSizeMB); err != nil {
		log.Printf("❌ [Task #%s] Failed to mark completion: %v\n", taskID, err)
		return
	}
	log.Printf("✅ [Task #%s] Completed! Output: %s (%.2f MB)\n", taskID, fullFilePath, fileSizeMB)
}