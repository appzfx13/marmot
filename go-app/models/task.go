package models

import "time"

// TaskParams represents the options dataset user parameters received from Django
type TaskParams struct {
	StartDate       string                 `json:"start_date"`
	EndDate         string                 `json:"end_date"`
	ExpiryDate      string                 `json:"expiry_date"`   // Option expiry date (YYYY-MM-DD), empty for INDEX tasks
	IndexName       string                 `json:"index_name"`
	SecurityID      string                 `json:"security_id"`
	ExchangeSegment string                 `json:"exchange_segment"`
	Instrument      string                 `json:"instrument"`
	StrikeCount     int                    `json:"strike_count"`
	UserID          string                 `json:"user_id"`
	BackupTaskID    string                 `json:"backup_task_id"`
	StrategyName    string                 `json:"strategy_name"`
	StrategyID      int                    `json:"strategy_id,omitempty"`
	ExecutionMode   string                 `json:"execution_mode,omitempty"`
	AccountID       int                    `json:"account_id,omitempty"`
	InitialCapital  float64                `json:"initial_capital"`
	
	// Optimizer parameters
	TargetMetric    string                 `json:"target_metric,omitempty"`
	RsiMin          int                    `json:"rsi_min,omitempty"`
	RsiMax          int                    `json:"rsi_max,omitempty"`
	EmaMin          int                    `json:"ema_min,omitempty"`
	EmaMax          int                    `json:"ema_max,omitempty"`
	Use30Days1s      bool                   `json:"use_30_days_1s"`
	Use30Days5s      bool                   `json:"use_30_days_5s"`
	IncludeVIX       bool                   `json:"include_vix"`
	IncludeMacro     bool                   `json:"include_macro"`
	MacroTimeframe   string                 `json:"macro_timeframe"`
	// FYERS authentication: app_id and access_token injected by Django
	FyersAppID       string                 `json:"fyers_app_id"`
	FyersAccessToken string                 `json:"fyers_access_token"`
	// FOREX / Databento parameters
	MarketType      string                 `json:"market_type"`
	ForexInstrument string                 `json:"forex_instrument"`
	ProviderName    string                 `json:"provider_name"`
	DatabentoAPIKey string                 `json:"databento_api_key"`
	DatabentoSchema string                 `json:"databento_schema"`
	// FOREX / CFD (OANDA) parameters
	CFDInstrument    string                `json:"cfd_instrument"`
	OandaGranularity string                `json:"oanda_granularity"`
	OandaAPIToken    string                `json:"oanda_api_token"`
	OandaEnvironment string                `json:"oanda_environment"`
	FrozenRulesSnapshot []map[string]interface{}  `json:"frozen_rules_snapshot,omitempty"`
	FrozenParameters    map[string]interface{}    `json:"frozen_parameters,omitempty"`
	Params              map[string]interface{}    `json:"params"`
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
	IncludeVIX      bool      `db:"include_vix" json:"include_vix"`
	IncludeMacro    bool      `db:"include_macro" json:"include_macro"`
	HasVIXData      bool      `db:"has_vix_data" json:"has_vix_data"`
	HasMacroData    bool      `db:"has_macro_data" json:"has_macro_data"`
	Status          string    `db:"status" json:"status"`
	Progress        int       `db:"progress" json:"progress"`
	ParquetFilePath string    `db:"parquet_file_path" json:"parquet_file_path"`
	FileSizeMB      float64   `db:"file_size_mb" json:"file_size_mb"`
	ErrorLogs       string    `db:"error_logs" json:"error_logs"`
	CreatedAt       time.Time `db:"created_at" json:"created_at"`
	UpdatedAt       time.Time `db:"updated_at" json:"updated_at"`
}