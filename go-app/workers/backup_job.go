package workers

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"go-app/models"
	"go-app/services"
)

// BackupJob handles the downloading, processing, and Parquet serialization logic
type BackupJob struct {
	dbService *services.DBService
	payload   models.CommandPayload
}

// NewBackupJob creates a new instance of BackupJob
func NewBackupJob(dbService *services.DBService, payload models.CommandPayload) *BackupJob {
	return &BackupJob{
		dbService: dbService,
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

	// Simulated batch processing steps (10% -> 90%)
	for progress := 10; progress <= 90; progress += 10 {
		select {
		case <-ctx.Done():
			// Context cancelled due to PAUSE, CANCEL, or container shutdown
			log.Printf("⏸️ [Task #%s] Execution loop interrupted by control command.\n", taskID)
			return
		case <-time.After(1 * time.Second): // Simulates batch network fetch & serialization
			log.Printf("📊 [Task #%s] Backup Progress: %d%%\n", taskID, progress)
			if err := j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress); err != nil {
				log.Printf("⚠️ [Task #%s] Failed to update progress: %v\n", taskID, err)
			}
		}
	}

	// Define destination output directory and file path
	outputDir := "/app/data/backups"
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		errorMsg := fmt.Sprintf("Failed to create storage directory: %v", err)
		log.Printf("❌ [Task #%s] %s\n", taskID, errorMsg)
		_ = j.dbService.RecordError(ctx, taskID, errorMsg)
		return
	}

	fileName := fmt.Sprintf("%s_%s_%s.parquet", indexName, taskID, time.Now().Format("20060102_150405"))
	fullFilePath := filepath.Join(outputDir, fileName)

	// Simulate saving file
	sampleData := []byte("PAR1_MARKET_BACKUP_PARQUET_FILE_DATA")
	if err := os.WriteFile(fullFilePath, sampleData, 0644); err != nil {
		errorMsg := fmt.Sprintf("Failed to write parquet file: %v", err)
		log.Printf("❌ [Task #%s] %s\n", taskID, errorMsg)
		_ = j.dbService.RecordError(ctx, taskID, errorMsg)
		return
	}

	// Calculate file size in MB
	fileInfo, err := os.Stat(fullFilePath)
	var fileSizeMB float64 = 0.01
	if err == nil {
		fileSizeMB = float64(fileInfo.Size()) / (1024 * 1024)
	}

	// Mark task completed in database (100% progress)
	if err := j.dbService.MarkTaskComplete(ctx, taskID, fullFilePath, fileSizeMB); err != nil {
		log.Printf("❌ [Task #%s] Failed to mark completion in DB: %v\n", taskID, err)
		return
	}

	log.Printf("✅ [Task #%s] Completed successfully! Parquet output: %s (%.2f MB)\n",
		taskID, fullFilePath, fileSizeMB)
}