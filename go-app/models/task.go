package models

import "time"

// TaskParams represents the options dataset user parameters received from Django
type TaskParams struct {
	StartDate      string `json:"start_date"`
	EndDate        string `json:"end_date"`
	IndexName      string `json:"index_name"`
	SecurityID     string `json:"security_id"`
	ExchangeSegment string `json:"exchange_segment"`
	Instrument     string `json:"instrument"`
	StrikeCount    int    `json:"strike_count"`
}

// CommandPayload represents the JSON IPC command sent over Redis channel
type CommandPayload struct {
	TaskID  string     `json:"task_id"`
	Command string     `json:"command"` // START, PAUSE, RESUME, CANCEL
	Params  TaskParams `json:"params"`
}

// MarketBackupTask represents the shared PostgreSQL database row
type MarketBackupTask struct {
	ID              string    `db:"id" json:"id"`
	StartDate       time.Time `db:"start_date" json:"start_date"`
	EndDate         time.Time `db:"end_date" json:"end_date"`
	IndexName       string    `db:"index_name" json:"index_name"`
	SecurityID      string    `db:"security_id" json:"security_id"`
	ExchangeSegment string    `db:"exchange_segment" json:"exchange_segment"`
	Instrument      string    `db:"instrument" json:"instrument"`
	StrikeCount     int       `db:"strike_count" json:"strike_count"`
	Status          string    `db:"status" json:"status"`
	Progress        int       `db:"progress" json:"progress"`
	ParquetFilePath string    `db:"parquet_file_path" json:"parquet_file_path"`
	FileSizeMB      float64   `db:"file_size_mb" json:"file_size_mb"`
	ErrorLogs       string    `db:"error_logs" json:"error_logs"`
	CreatedAt       time.Time `db:"created_at" json:"created_at"`
	UpdatedAt       time.Time `db:"updated_at" json:"updated_at"`
}