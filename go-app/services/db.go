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
)

type DBService struct {
	Pool      *pgxpool.Pool
	TableName string
}

func NewDBService(ctx context.Context, dbURL, tableName string) (*DBService, error) {
	pool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		return nil, fmt.Errorf("unable to connect to postgres: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		return nil, fmt.Errorf("postgres ping failed: %w", err)
	}

	log.Println("✅ Connected to PostgreSQL (Shared State Layer)")
	return &DBService{Pool: pool, TableName: tableName}, nil
}

// UpdateTaskProgress updates status and progress percentage (0 to 100)
func (s *DBService) UpdateTaskProgress(ctx context.Context, taskID string, status string, progress int) error {
	query := fmt.Sprintf(`
		UPDATE %s 
		SET status = $1, progress = $2, updated_at = $3 
		WHERE id = $4
	`, s.TableName)

	_, err := s.Pool.Exec(ctx, query, status, progress, time.Now(), taskID)
	if err != nil {
		log.Printf("❌ DB Update Error [Task %s]: %v\n", taskID, err)
		return err
	}
	return nil
}

// UpdateTaskStatus updates only the status
func (s *DBService) UpdateTaskStatus(ctx context.Context, taskID string, status string) error {
	query := fmt.Sprintf(`
		UPDATE %s 
		SET status = $1, updated_at = $2 
		WHERE id = $3
	`, s.TableName)

	_, err := s.Pool.Exec(ctx, query, status, time.Now(), taskID)
	if err != nil {
		log.Printf("❌ DB Update Status Error [Task %s]: %v\n", taskID, err)
		return err
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

// MarkTaskComplete marks job as completed, sets progress to 100%, and updates file details
func (s *DBService) MarkTaskComplete(ctx context.Context, taskID string, filePath string, fileSizeMB float64) error {
	query := fmt.Sprintf(`
		UPDATE %s 
		SET status = 'completed', progress = 100, parquet_file_path = $1, file_size_mb = $2, updated_at = $3 
		WHERE id = $4
	`, s.TableName)

	_, err := s.Pool.Exec(ctx, query, filePath, fileSizeMB, time.Now(), taskID)
	if err != nil {
		log.Printf("❌ DB Completion Update Error [Task %s]: %v\n", taskID, err)
		return err
	}
	return nil
}

// RecordError updates task status to 'error', resets file path/size to NULL/0.0, and appends timestamped error details
func (s *DBService) RecordError(ctx context.Context, taskID string, errorMsg string) error {
	query := fmt.Sprintf(`
		UPDATE %s 
		SET status = 'error', 
		    parquet_file_path = NULL,
		    file_size_mb = 0.0,
		    error_logs = CASE 
		        WHEN error_logs IS NULL OR error_logs = '' THEN $1 
		        ELSE error_logs || E'\n' || $1 
		    END, 
		    updated_at = $2 
		WHERE id = $3
	`, s.TableName)

	_, err := s.Pool.Exec(ctx, query, errorMsg, time.Now(), taskID)
	if err != nil {
		log.Printf("❌ DB Error Log Update Error [Task %s]: %v\n", taskID, err)
		return err
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