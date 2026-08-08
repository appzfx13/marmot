package config

import (
	"fmt"
	"os"
)

type Config struct {
	DatabaseURL string
	RedisURL    string
	DBTableName     string
	WSPort          string
	DhanClientID    string
	DhanAccessToken string
}

func LoadConfig() *Config {
	dbHost := getEnv("DB_HOST", "db")
	dbPort := getEnv("DB_PORT", "5432")
	dbUser := getEnv("DB_USER", "postgres")
	dbPass := getEnv("DB_PASSWORD", "postgres")
	dbName := getEnv("DB_NAME", "marmot_db")

	// Construct PostgreSQL DSN URL
	dbURL := fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
		dbUser, dbPass, dbHost, dbPort, dbName)

	redisURL := getEnv("REDIS_URL", "redis://redis:6379/0")
	tableName := getEnv("DB_TABLE_NAME", "market_marketbackuptask")
	wsPort := getEnv("WS_PORT", "8081")
	dhanClient := getEnv("DHAN_CLIENT_ID", "")
	dhanToken := getEnv("DHAN_ACCESS_TOKEN", "")

	return &Config{
		DatabaseURL:     dbURL,
		RedisURL:        redisURL,
		DBTableName:     tableName,
		WSPort:          wsPort,
		DhanClientID:    dhanClient,
		DhanAccessToken: dhanToken,
	}
}

// Helper to retrieve environment variables with a fallback default
func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists && value != "" {
		return value
	}
	return fallback
}