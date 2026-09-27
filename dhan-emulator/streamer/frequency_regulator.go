package streamer

import (
	"fmt"
	"sync"
	"time"
)

// FrequencyRegulator coordinates multi-timeframe clock synchronization and dynamic pacing.
type FrequencyRegulator struct {
	mu             sync.RWMutex
	virtualTime    time.Time
	lastSpotMinute string
	speed          int
	profileKey     string
	subTickStep    time.Duration
	spotStep       time.Duration
	lastEmitTime   time.Time
	tickCount      int64
}

// NewFrequencyRegulator initializes the frequency matching and pacing governor.
func NewFrequencyRegulator(speed int, profileKey string) *FrequencyRegulator {
	if speed <= 0 {
		speed = 1
	}
	if profileKey == "" {
		profileKey = "COMPRESSED"
	}
	return &FrequencyRegulator{
		speed:       speed,
		profileKey:  profileKey,
		subTickStep: 5 * time.Second,
		spotStep:    60 * time.Second,
	}
}

// SetSpeed updates playback multiplier and profile dynamically.
func (fr *FrequencyRegulator) SetSpeed(speed int, profileKey string) {
	fr.mu.Lock()
	defer fr.mu.Unlock()
	if speed <= 0 {
		speed = 1
	}
	fr.speed = speed
	fr.profileKey = profileKey
}

// OnTick synchronizes virtual clock, detects 1-minute Spot rollovers, and computes 5s sub-tick offsets.
func (fr *FrequencyRegulator) OnTick(recordTime time.Time) (isNewSpotBar bool, subTickIdx int, subTickLabel string) {
	fr.mu.Lock()
	defer fr.mu.Unlock()

	fr.virtualTime = recordTime
	fr.tickCount++

	minuteStr := recordTime.Format("2006-01-02 15:04")
	if fr.lastSpotMinute == "" || minuteStr != fr.lastSpotMinute {
		fr.lastSpotMinute = minuteStr
		isNewSpotBar = true
	}

	second := recordTime.Second()
	subTickIdx = second / 5
	barChar := byte('A' + ((recordTime.Minute()) % 26))
	subTickLabel = fmt.Sprintf("%c.%02d", barChar, second)

	return isNewSpotBar, subTickIdx, subTickLabel
}

// GetPacingSleep calculates the exact sleep duration for the given tick interval and playback profile.
func (fr *FrequencyRegulator) GetPacingSleep(stepDuration time.Duration) time.Duration {
	fr.mu.RLock()
	speed := fr.speed
	profKey := fr.profileKey
	fr.mu.RUnlock()

	if stepDuration <= 10*time.Second {
		// 5-Second Micro Resolution Dataset
		switch {
		case profKey == "REALTIME" || profKey == "REAL":
			return 5000 * time.Millisecond
		default:
			// In COMPRESSED mode (speed=1), 1 virtual minute (12 ticks) should take 1 real second.
			// 1000ms / 12 ticks = 83ms per tick.
			// If speed is faster, we divide proportionally.
			d := time.Duration(1000/(speed*12)) * time.Millisecond
			if d < 4*time.Millisecond {
				d = 4 * time.Millisecond
			}
			return d
		}
	}

	// 1-Minute Macro Resolution Dataset
	switch {
	case profKey == "REALTIME" || profKey == "REAL":
		return 60 * time.Second
	default:
		d := time.Duration(1000/speed) * time.Millisecond
		if d < 4*time.Millisecond {
			d = 4 * time.Millisecond
		}
		return d
	}
}

// CurrentVirtualTime returns the latest synchronized virtual clock timestamp.
func (fr *FrequencyRegulator) CurrentVirtualTime() time.Time {
	fr.mu.RLock()
	defer fr.mu.RUnlock()
	return fr.virtualTime
}

// Reset clears the regulator state for a fresh replay session.
func (fr *FrequencyRegulator) Reset() {
	fr.mu.Lock()
	defer fr.mu.Unlock()
	fr.virtualTime = time.Time{}
	fr.lastSpotMinute = ""
	fr.tickCount = 0
	fr.lastEmitTime = time.Time{}
}
