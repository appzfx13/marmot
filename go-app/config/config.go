package config

import (
	"fmt"
	"os"
)

type Config struct {
	DatabaseURL string
	RedisURL    string
	DBTableName string
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

	return &Config{
		DatabaseURL: dbURL,
		RedisURL:    redisURL,
		DBTableName: tableName,
	}
}

// Helper to retrieve environment variables with a fallback default
func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists && value != "" {
		return value
	}
	return fallback
}