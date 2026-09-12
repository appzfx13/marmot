package engine

import (
	"strings"
	"sync"
	"time"
)

// ChaosMode defines the chaos state for order processing and webhooks.
type ChaosMode string

const (
	ChaosModeNormal        ChaosMode = "NORMAL"
	ChaosModeDropWebhooks  ChaosMode = "DROP_WEBHOOKS"
	ChaosModeDelayWebhooks ChaosMode = "DELAY_WEBHOOKS"
)

// ChaosManager manages rate limiting, chaos simulation, and synthetic failure triggers.
type ChaosManager struct {
	mu            sync.RWMutex
	rateLimitRPS  int
	tokens        float64
	maxTokens     float64
	lastRefill    time.Time
	mode          ChaosMode
	webhookDelay  time.Duration
	rejectRatePct int // 0 to 100% synthetic random rejection
}

// NewChaosManager initializes a new ChaosManager.
func NewChaosManager(rps int) *ChaosManager {
	if rps <= 0 {
		rps = 20
	}
	return &ChaosManager{
		rateLimitRPS:  rps,
		tokens:        float64(rps),
		maxTokens:     float64(rps),
		lastRefill:    time.Now(),
		mode:          ChaosModeNormal,
		webhookDelay:  6 * time.Second,
		rejectRatePct: 0,
	}
}

// AllowRequest checks if an incoming API request can proceed under the token-bucket rate limiter.
func (c *ChaosManager) AllowRequest() bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(c.lastRefill).Seconds()
	c.lastRefill = now

	// Refill tokens based on elapsed time and configured RPS
	c.tokens += elapsed * float64(c.rateLimitRPS)
	if c.tokens > c.maxTokens {
		c.tokens = c.maxTokens
	}

	if c.tokens >= 1.0 {
		c.tokens -= 1.0
		return true
	}
	return false
}

// CheckSyntheticError inspects order attributes (like correlationId or price) to inject deliberate broker errors.
func (c *ChaosManager) CheckSyntheticError(correlationID string, price float64) (bool, string) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	upperID := strings.ToUpper(correlationID)
	if strings.Contains(upperID, "ERR_MARGIN") {
		return true, "MARGIN_INSUFFICIENT: Insufficient virtual balance available"
	}
	if strings.Contains(upperID, "ERR_FREEZE") {
		return true, "ORDER_FREEZE_LIMIT_EXCEEDED: Quantity exceeds exchange single-order freeze limit"
	}
	if strings.Contains(upperID, "ERR_PRICE") {
		return true, "PRICE_OUT_OF_LMT_RANGE: Limit price is outside daily execution operating range"
	}
	if strings.Contains(upperID, "ERR_RISK") {
		return true, "RMS_REJECT: RMS risk rule block applied for account"
	}

	return false, ""
}

// GetMode returns current chaos mode.
func (c *ChaosManager) GetMode() ChaosMode {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.mode
}

// SetMode updates chaos mode.
func (c *ChaosManager) SetMode(mode ChaosMode) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.mode = mode
}

// GetRPS returns current Rate Limit RPS.
func (c *ChaosManager) GetRPS() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.rateLimitRPS
}

// SetRPS adjusts the token-bucket capacity and refill rate.
func (c *ChaosManager) SetRPS(rps int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if rps <= 0 {
		rps = 1
	}
	c.rateLimitRPS = rps
	c.maxTokens = float64(rps)
	if c.tokens > c.maxTokens {
		c.tokens = c.maxTokens
	}
}

// GetWebhookDelay returns configured delay duration when in ChaosModeDelayWebhooks.
func (c *ChaosManager) GetWebhookDelay() time.Duration {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.webhookDelay
}
