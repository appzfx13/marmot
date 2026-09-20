package services

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

type DBService struct {
	Pool      *pgxpool.Pool
	TableName string
	Rdb       *redis.Client
}

func NewDBService(ctx context.Context, dbURL, tableName string, rdb *redis.Client) (*DBService, error) {
	var pool *pgxpool.Pool
	var err error
	maxRetries := 10

	for attempt := 1; attempt <= maxRetries; attempt++ {
		pool, err = pgxpool.New(ctx, dbURL)
		if err == nil {
			if pingErr := pool.Ping(ctx); pingErr == nil {
				log.Println("✅ Connected to PostgreSQL (Shared State Layer)")
				return &DBService{Pool: pool, TableName: tableName, Rdb: rdb}, nil
			} else {
				err = pingErr
			}
			pool.Close()
		}

		if attempt < maxRetries {
			log.Printf("⏳ [DB] PostgreSQL not ready yet (%v). Retrying in 2s (Attempt %d/%d)...", err, attempt, maxRetries)
			time.Sleep(2 * time.Second)
		}
	}

	return nil, fmt.Errorf("unable to connect to postgres after %d attempts: %w", maxRetries, err)
}

// broadcastTaskEvent serializes the event into JSON and pushes it to Redis streams
func (s *DBService) broadcastTaskEvent(ctx context.Context, taskID, eventType string, payload map[string]interface{}) error {
	if s.Rdb == nil {
		log.Printf("⚠️ Redis client not initialized in DBService, cannot broadcast %s for task %s", eventType, taskID)
		return nil
	}
	
	msg := map[string]interface{}{
		"task_id":    taskID,
		"event_type": eventType,
		"timestamp":  time.Now().Unix(),
		"payload":    payload,
	}
	
	jsonBytes, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	
	return s.Rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: "marmot:tasks:control",
		Values: map[string]interface{}{
			"data": string(jsonBytes),
		},
	}).Err()
}

// UpdateTaskProgress writes status and progress to Postgres and broadcasts via Redis.
func (s *DBService) UpdateTaskProgress(ctx context.Context, taskID string, status string, progress int) error {
	query := fmt.Sprintf(`UPDATE %s SET status=$1, progress=$2, updated_at=NOW() WHERE id=$3`, s.TableName)
	if _, dbErr := s.Pool.Exec(ctx, query, status, progress, taskID); dbErr != nil {
		log.Printf("⚠️ [DB] UpdateTaskProgress PG write error [Task %s]: %v\n", taskID, dbErr)
	}
	payload := map[string]interface{}{"status": status, "progress": progress}
	if err := s.broadcastTaskEvent(ctx, taskID, "progress_update", payload); err != nil {
		log.Printf("❌ Redis Broadcast Error [Task %s]: %v\n", taskID, err)
	}
	return nil
}

// UpdateTaskStatus writes status to Postgres and broadcasts via Redis.
func (s *DBService) UpdateTaskStatus(ctx context.Context, taskID string, status string) error {
	query := fmt.Sprintf(`UPDATE %s SET status=$1, updated_at=NOW() WHERE id=$2`, s.TableName)
	if _, dbErr := s.Pool.Exec(ctx, query, status, taskID); dbErr != nil {
		log.Printf("⚠️ [DB] UpdateTaskStatus PG write error [Task %s]: %v\n", taskID, dbErr)
	}
	payload := map[string]interface{}{"status": status}
	if err := s.broadcastTaskEvent(ctx, taskID, "status_update", payload); err != nil {
		log.Printf("❌ Redis Broadcast Error [Task %s]: %v\n", taskID, err)
	}
	return nil
}

// GetTaskProgress retrieves the current progress percentage from the DB
func (s *DBService) GetTaskProgress(ctx context.Context, taskID string) (int, error) {
	query := fmt.Sprintf(`SELECT progress FROM %s WHERE id = $1`, s.TableName)
	var progress int
	err := s.Pool.QueryRow(ctx, query, taskID).Scan(&progress)
	if err != nil {
		log.Printf("❌ DB Get Progress Error [Task %s]: %v\n", taskID, err)
		return 0, err
	}
	return progress, nil
}

// MarkTaskComplete writes completed state, 100% progress, and file details to Postgres and broadcasts via Redis.
func (s *DBService) MarkTaskComplete(ctx context.Context, taskID string, filePath string, fileSizeMB float64) error {
	query := fmt.Sprintf(`UPDATE %s SET status='completed', progress=100, parquet_file_path=$1, file_size_mb=$2, updated_at=NOW() WHERE id=$3`, s.TableName)
	if _, dbErr := s.Pool.Exec(ctx, query, filePath, fileSizeMB, taskID); dbErr != nil {
		log.Printf("⚠️ [DB] MarkTaskComplete PG write error [Task %s]: %v\n", taskID, dbErr)
	}
	payload := map[string]interface{}{
		"status":            "completed",
		"progress":          100,
		"parquet_file_path": filePath,
		"file_size_mb":      fileSizeMB,
	}
	if err := s.broadcastTaskEvent(ctx, taskID, "task_completed", payload); err != nil {
		log.Printf("❌ Redis Broadcast Error [Task %s]: %v\n", taskID, err)
	}
	return nil
}

// RecordError writes error state and message to Postgres and broadcasts via Redis.
func (s *DBService) RecordError(ctx context.Context, taskID string, errorMsg string) error {
	query := fmt.Sprintf(`UPDATE %s SET status='error', error_logs=$1, updated_at=NOW() WHERE id=$2`, s.TableName)
	if _, dbErr := s.Pool.Exec(ctx, query, errorMsg, taskID); dbErr != nil {
		log.Printf("⚠️ [DB] RecordError PG write error [Task %s]: %v\n", taskID, dbErr)
	}
	payload := map[string]interface{}{"status": "error", "error_logs": errorMsg}
	if err := s.broadcastTaskEvent(ctx, taskID, "task_error", payload); err != nil {
		log.Printf("❌ Redis Broadcast Error [Task %s]: %v\n", taskID, err)
	}
	return nil
}

// Close gracefully releases PostgreSQL database connections in pool
func (s *DBService) Close() {
	if s.Pool != nil {
		s.Pool.Close()
	}
}

// GetLastIndexClose returns the most recent close price for a given index
// by looking up the latest completed INDEX backup task in the market_marketbackuptask table.
// Returns (price, nil) on success, (0, error) if no data is available.
// The options download uses this to calculate ATM without needing a live feed.
func (s *DBService) GetLastIndexClose(ctx context.Context, indexName string) (float64, error) {
	// Find the latest completed backup task for this index that has index data
	query := fmt.Sprintf(`
		SELECT parquet_file_path FROM %s
		WHERE index_name = $1
		  AND status = 'completed'
		  AND parquet_file_path IS NOT NULL
		  AND parquet_file_path != ''
		ORDER BY end_date DESC
		LIMIT 1
	`, s.TableName)

	var filePath string
	err := s.Pool.QueryRow(ctx, query, indexName).Scan(&filePath)
	if err != nil {
		return 0, fmt.Errorf("no completed backup task found for index %s: %w", indexName, err)
	}

	log.Printf("[DB] GetLastIndexClose: reading parquet path=%s for index=%s", filePath, indexName)

	// Read the most recent .parquet (newline-delimited JSON) file under the path
	closePrice, readErr := readLastCloseFromParquetDir(filePath)
	if readErr != nil {
		return 0, fmt.Errorf("could not read close price from %s: %w", filePath, readErr)
	}

	log.Printf("[DB] GetLastIndexClose: %s last close=%.2f", indexName, closePrice)
	return closePrice, nil
}

// readLastCloseFromParquetDir walks a parquet directory and returns the last close price
// from the most recent newline-delimited JSON file.
func readLastCloseFromParquetDir(dirPath string) (float64, error) {
	var files []string
	_ = filepath.Walk(dirPath, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && strings.HasSuffix(path, ".parquet") {
			files = append(files, path)
		}
		return nil
	})

	if len(files) == 0 {
		return 0, fmt.Errorf("no parquet files found in %s", dirPath)
	}

	// Sort files so the most recent date is last
	sort.Strings(files)
	latestFile := files[len(files)-1]

	f, err := os.Open(latestFile)
	if err != nil {
		return 0, fmt.Errorf("open %s: %w", latestFile, err)
	}
	defer f.Close()

	// Read all lines and take the last non-empty one
	var lastLine string
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		if line := strings.TrimSpace(scanner.Text()); line != "" {
			lastLine = line
		}
	}

	if lastLine == "" {
		return 0, fmt.Errorf("file %s is empty", latestFile)
	}

	var candle map[string]interface{}
	if err := json.Unmarshal([]byte(lastLine), &candle); err != nil {
		return 0, fmt.Errorf("parse candle JSON: %w", err)
	}

	closeVal, ok := candle["close"].(float64)
	if !ok || closeVal <= 0 {
		return 0, fmt.Errorf("invalid close value in candle: %v", candle["close"])
	}

	return closeVal, nil
}

// GetBrokerCredentials retrieves FYERS App ID, Access Token, Token Date, and active status from common_sitesettings.
func (s *DBService) GetBrokerCredentials(ctx context.Context) (string, string, bool, *time.Time, error) {
	var appID, token string
	var isActive bool
	var tokenDate *time.Time
	query := `SELECT COALESCE(fyers_app_id, ''), COALESCE(fyers_access_token, ''), fyers_feed_is_active, fyers_token_generated_date FROM common_sitesettings ORDER BY id LIMIT 1`
	err := s.Pool.QueryRow(ctx, query).Scan(&appID, &token, &isActive, &tokenDate)
	if err != nil {
		return "", "", false, nil, fmt.Errorf("failed to fetch broker credentials: %w", err)
	}
	return appID, token, isActive, tokenDate, nil
}
