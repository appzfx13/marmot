package services

import (
	"context"
	"fmt"
	"log"

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

	client := redis.NewClient(opt)
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping failed: %w", err)
	}

	log.Println("✅ Connected to Redis (Pub/Sub IPC Broker)")
	return &RedisService{Client: client}, nil
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