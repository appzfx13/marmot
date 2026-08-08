package services

import (
	"context"
	"fmt"
	"log"
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

// RecordError updates task status to 'error' and writes timestamped error details
func (s *DBService) RecordError(ctx context.Context, taskID string, errorMsg string) error {
	query := fmt.Sprintf(`
		UPDATE %s 
		SET status = 'error', error_logs = $1, updated_at = $2 
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