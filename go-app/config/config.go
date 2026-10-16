package config

import (
	"fmt"
	"os"
)

type Config struct {
	DatabaseURL          string
	RedisURL             string
	DBTableName          string
	WSPort               string
	DatabentoAPIKey      string
	OandaAPIToken        string
	OandaEnvironment     string
	SandboxBrokerBaseURL string
	SandboxBrokerClientID string
	SandboxBrokerToken   string
}

func LoadConfig() *Config {
	dbHost := getEnv("POSTGRES_HOST", "db")           
	dbPort := getEnv("POSTGRES_PORT", "5432")
	dbUser := getEnv("POSTGRES_USER", "postgres")
	dbPass := getEnv("POSTGRES_PASSWORD", "postgres")
	dbName := getEnv("POSTGRES_DB", "marmot_db")

	// Construct PostgreSQL DSN URL
	dbURL := fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
		dbUser, dbPass, dbHost, dbPort, dbName)

	redisURL := getEnv("REDIS_URL", "redis://redis_broker:6379/0")
	tableName := getEnv("DB_TABLE_NAME", "market_marketbackuptask")
	wsPort := getEnv("WS_PORT", "8082")
	databentoKey := os.Getenv("DATABENTO_API_KEY")
	oandaToken := os.Getenv("OANDA_API_TOKEN")
	oandaEnv := getEnv("OANDA_ENVIRONMENT", "practice")

	sandboxURL := getEnv("SANDBOX_BROKER_BASE_URL", "https://pep-erratic-violate.ngrok-free.dev")
	sandboxClientID := getEnv("SANDBOX_BROKER_CLIENT_ID", "1072641686")
	sandboxToken := getEnv("SANDBOX_BROKER_ACCESS_TOKEN", "dhn_sec_sandbox_u3XsDKCFKyelHn2ARPYwMlmU7ujHYVjO")

	cfg := &Config{
		DatabaseURL:          dbURL,
		RedisURL:             redisURL,
		DBTableName:          tableName,
		WSPort:               wsPort,
		DatabentoAPIKey:      databentoKey,
		OandaAPIToken:        oandaToken,
		OandaEnvironment:     oandaEnv,
		SandboxBrokerBaseURL: sandboxURL,
		SandboxBrokerClientID: sandboxClientID,
		SandboxBrokerToken:   sandboxToken,
	}

	// DEBUG: Log loaded config values
	fmt.Println("========== [CONFIG DEBUG] ==========")
	fmt.Printf("[CONFIG] POSTGRES_HOST  (POSTGRES_HOST) : %s\n", dbHost)
	fmt.Printf("[CONFIG] DB_PORT        (POSTGRES_PORT) : %s\n", dbPort)
	fmt.Printf("[CONFIG] DB_USER        (POSTGRES_USER) : %s\n", dbUser)
	fmt.Printf("[CONFIG] DB_NAME        (POSTGRES_DB)   : %s\n", dbName)
	fmt.Printf("[CONFIG] DB_PASSWORD    (POSTGRES_PASS) : %s\n", maskSecret(dbPass))
	fmt.Printf("[CONFIG] DatabaseURL                    : %s\n", maskDBURL(dbURL))
	fmt.Printf("[CONFIG] RedisURL       (REDIS_URL)     : %s\n", redisURL)
	fmt.Printf("[CONFIG] DBTableName    (DB_TABLE_NAME) : %s\n", tableName)
	fmt.Printf("[CONFIG] WSPort         (WS_PORT)       : %s\n", wsPort)
	fmt.Println("=====================================")

	return cfg
}

func debugTokenPreview(s string) string {
	if s == "" {
		return "<EMPTY>"
	}
	if len(s) > 12 {
		return s[:6] + "..." + s[len(s)-4:]
	}
	return s
}


// maskSecret hides all but the first 4 chars of a secret for safe logging
func maskSecret(s string) string {
	if len(s) <= 4 {
		return "****"
	}
	return s[:4] + "****"
}

// maskDBURL hides the password in a postgres:// URL for safe logging
func maskDBURL(url string) string {
	// Simple masking: replace password portion
	// Format: postgres://user:pass@host:port/db
	for i, c := range url {
		if c == ':' {
			// find the second colon (after user)
			rest := url[i+1:]
			at := -1
			for j, ch := range rest {
				if ch == '@' {
					at = j
					break
				}
			}
			if at > 0 {
				return url[:i+1] + "****" + "@" + rest[at+1:]
			}
		}
	}
	return url
}

// Helper to retrieve environment variables with explicit warning log if default is used
func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists && value != "" {
		return value
	}
	if fallback != "" {
		fmt.Printf("⚠️ [CONFIG] Environment variable '%s' not set. Using fallback: '%s'\n", key, fallback)
	}
	return fallback
}