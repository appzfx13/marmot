package services

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/redis/go-redis/v9"
)

const (
	// DefaultRedisChannel is the fallback global channel your WebSocket/Django worker subscribes to
	DefaultRedisChannel = "global_events_channel"
	// DefaultHashSecret is used only if HASH_SECRET_KEY is not defined in .env
	DefaultHashSecret = "your-default-shared-secret-key"
)

// SystemEvent represents a generic payload sent to the frontend for UI updates & toasts
type SystemEvent struct {
	Topic         string                 `json:"topic"`                      // e.g., "logs_table", "user_notifications", "exports"
	EventType     string                 `json:"event_type"`                 // e.g., "REFRESH_TABLE", "SHOW_TOAST", "WORKER_COMPLETE"
	Status        string                 `json:"status"`                     // "SUCCESS", "FAILED", "PROCESSING", "INFO"
	Message       string                 `json:"message"`                    // Toast message text
	TargetUserIDs []int64                `json:"target_user_ids,omitempty"` // Specific user IDs (empty = global)
	TargetGroup   string                 `json:"target_group,omitempty"`    // Specific tenant/role group (e.g. "trader_10")
	Data          map[string]interface{} `json:"data,omitempty"`            // Extra payload (ID, metadata, etc.)
}

type NotifierService struct {
	rdb        *redis.Client
	channel    string
	hashSecret []byte
}

// NewNotifierService initializes a new service instance connected to Redis & loads secret key from .env
func NewNotifierService() *NotifierService {
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://127.0.0.1:6379/0"
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Printf("[NotifierService WARNING] Failed to parse REDIS_URL ('%s'): %v. Falling back to default options.", redisURL, err)
		opt = &redis.Options{
			Addr: "127.0.0.1:6379",
			DB:   0,
		}
	}

	// 1. Fetch secret key from .env for HMAC hashing
	secretStr := os.Getenv("HASH_SECRET_KEY")
	if secretStr == "" {
		log.Printf("[NotifierService WARNING] HASH_SECRET_KEY not set in .env. Falling back to default secret.")
		secretStr = DefaultHashSecret
	}

	client := redis.NewClient(opt)

	return &NotifierService{
		rdb:        client,
		channel:    DefaultRedisChannel,
		hashSecret: []byte(secretStr),
	}
}

// NewNotifierServiceWithClient allows injecting an existing Redis client instance
func NewNotifierServiceWithClient(rdb *redis.Client, channel string, hashSecret string) *NotifierService {
	if channel == "" {
		channel = DefaultRedisChannel
	}
	if hashSecret == "" {
		hashSecret = DefaultHashSecret
	}
	return &NotifierService{
		rdb:        rdb,
		channel:    channel,
		hashSecret: []byte(hashSecret),
	}
}

// HashUserID creates a deterministic HMAC-SHA256 hex string for a given user ID (Method 1)
func (n *NotifierService) HashUserID(userID int64) string {
	h := hmac.New(sha256.New, n.hashSecret)
	h.Write([]byte(fmt.Sprintf("%d", userID)))
	return hex.EncodeToString(h.Sum(nil))
}

// PublishEvent broadcasts a global real-time event to all connected clients
func (n *NotifierService) PublishEvent(ctx context.Context, event SystemEvent) error {
	return n.publishToChannel(ctx, n.channel, event, "Global Broadcast")
}

// PublishToUser broadcasts a real-time event exclusively to a hashed user channel
func (n *NotifierService) PublishToUser(ctx context.Context, userID int64, event SystemEvent) error {
	event.TargetUserIDs = []int64{userID}

	// Method 1: Hash the user ID before generating the channel name
	hashedID := n.HashUserID(userID)
	userChannel := fmt.Sprintf("user_events_%s", hashedID)

	return n.publishToChannel(ctx, userChannel, event, fmt.Sprintf("User [%d -> %s...]", userID, hashedID[:8]))
}

// PublishToUsers broadcasts a real-time event to a list of specified user IDs
func (n *NotifierService) PublishToUsers(ctx context.Context, userIDs []int64, event SystemEvent) error {
	event.TargetUserIDs = userIDs

	for _, userID := range userIDs {
		hashedID := n.HashUserID(userID)
		userChannel := fmt.Sprintf("user_events_%s", hashedID)

		if err := n.publishToChannel(ctx, userChannel, event, fmt.Sprintf("User [%d -> %s...]", userID, hashedID[:8])); err != nil {
			return err
		}
	}

	return nil
}

// PublishToGroup broadcasts an event to a designated group/tenant (e.g., "trader_12", "admins")
func (n *NotifierService) PublishToGroup(ctx context.Context, group string, event SystemEvent) error {
	event.TargetGroup = group
	groupChannel := fmt.Sprintf("group_events_%s", group)

	return n.publishToChannel(ctx, groupChannel, event, fmt.Sprintf("Group [%s]", group))
}

// Internal helper method to handle marshaling, logging, and Redis publishing
func (n *NotifierService) publishToChannel(ctx context.Context, targetChannel string, event SystemEvent, targetLabel string) error {
	payload, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal system event: %w", err)
	}

	// 1. Diagnostics Log
	log.Printf("[Notifier -> %s] [%s] Topic: %s | Status: %s | Msg: %s",
		targetLabel, event.EventType, event.Topic, event.Status, event.Message)

	// 2. Publish to Redis channel
	if n.rdb != nil {
		err := n.rdb.Publish(ctx, targetChannel, payload).Err()
		if err != nil {
			return fmt.Errorf("failed to publish event to redis channel %s: %w", targetChannel, err)
		}
	} else {
		log.Printf("[NotifierService WARNING] Redis client is uninitialized. Skipping publish.")
	}

	return nil
}

// Close closes the underlying Redis connection pool cleanly
func (n *NotifierService) Close() error {
	if n.rdb != nil {
		return n.rdb.Close()
	}
	return nil
}