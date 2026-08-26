package services

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/redis/go-redis/v9"
)

type RedisService struct {
	Client *redis.Client
}

// NewRedisService parses the Redis URL, establishes a connection, and verifies it with a Ping
func NewRedisService(ctx context.Context, redisURL string) (*RedisService, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("invalid redis url: %w", err)
	}

	var client *redis.Client
	maxRetries := 10

	for attempt := 1; attempt <= maxRetries; attempt++ {
		client = redis.NewClient(opt)
		if pingErr := client.Ping(ctx).Err(); pingErr == nil {
			log.Println("✅ Connected to Redis (Pub/Sub IPC Broker)")
			return &RedisService{Client: client}, nil
		} else {
			err = pingErr
			client.Close()
		}

		if attempt < maxRetries {
			log.Printf("⏳ [Redis] Redis broker not ready yet (%v). Retrying in 2s (Attempt %d/%d)...", err, attempt, maxRetries)
			time.Sleep(2 * time.Second)
		}
	}

	return nil, fmt.Errorf("unable to connect to redis after %d attempts: %w", maxRetries, err)
}

// Subscribe returns a Redis PubSub object listening to the specified Pub/Sub channel
func (s *RedisService) Subscribe(ctx context.Context, channel string) *redis.PubSub {
	return s.Client.Subscribe(ctx, channel)
}

// Close gracefully releases the Redis connection
func (s *RedisService) Close() {
	if s.Client != nil {
		s.Client.Close()
	}
}