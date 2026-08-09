package workers

import (
	"encoding/csv"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const (
	dhanScripMasterURL  = "https://images.dhan.co/api-data/api-scrip-master.csv"
	scripMasterCacheDir = "/app/data/scrip_master"
)

// ScripMaster holds all loaded option entries indexed for fast lookup
type ScripMaster struct {
	// key: "UNDERLYING|EXPIRY|STRIKE|OPTTYPE" -> SecurityID
	index map[string]string
}

// LoadScripMaster downloads (or loads from cache) and parses the Dhan scrip master CSV.
// Cache is refreshed daily: /app/data/scrip_master/YYYY-MM-DD.csv
func LoadScripMaster() (*ScripMaster, error) {
	_ = os.MkdirAll(scripMasterCacheDir, 0755)

	today := time.Now().Format("2006-01-02")
	cachePath := filepath.Join(scripMasterCacheDir, today+".csv")

	if _, err := os.Stat(cachePath); os.IsNotExist(err) {
		log.Printf("[SCRIP] Downloading Dhan scrip master CSV from %s", dhanScripMasterURL)
		if dlErr := downloadScripFile(dhanScripMasterURL, cachePath); dlErr != nil {
			return nil, fmt.Errorf("scrip master download failed: %w", dlErr)
		}
		log.Printf("[SCRIP] Scrip master saved to %s", cachePath)
	} else {
		log.Printf("[SCRIP] Using cached scrip master: %s", cachePath)
	}

	return parseScripMaster(cachePath)
}

func downloadScripFile(url, dest string) error {
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d fetching scrip master", resp.StatusCode)
	}

	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = io.Copy(f, resp.Body)
	return err
}

func parseScripMaster(path string) (*ScripMaster, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open scrip master: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	reader.LazyQuotes = true
	reader.TrimLeadingSpace = true

	headers, err := reader.Read()
	if err != nil {
		return nil, fmt.Errorf("read scrip master header: %w", err)
	}

	// Build column index map (lowercase for case-insensitive matching)
	colIdx := make(map[string]int)
	for i, h := range headers {
		colIdx[strings.ToLower(strings.TrimSpace(h))] = i
	}

	getCol := func(row []string, names ...string) string {
		for _, name := range names {
			if i, ok := colIdx[name]; ok && i < len(row) {
				if v := strings.TrimSpace(row[i]); v != "" {
					return v
				}
			}
		}
		return ""
	}

	sm := &ScripMaster{index: make(map[string]string)}
	rowCount := 0

	for {
		row, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}

		instrument := getCol(row, "instrument")
		if instrument != "OPTIDX" {
			continue
		}

		secID := getCol(row, "sm_security_id", "security_id", "sm_securityid")
		optType := strings.ToUpper(getCol(row, "option_type", "optiontype"))
		strikePriceStr := getCol(row, "strike_price", "strikeprice", "strikeprice")
		expiryRaw := getCol(row, "expiry_date", "expirydate", "expiry")
		underlying := strings.ToUpper(getCol(row, "underlying", "symbolname", "tradingsymbol"))

		if secID == "" || optType == "" || strikePriceStr == "" || expiryRaw == "" || underlying == "" {
			continue
		}

		expiry := normaliseScripDate(expiryRaw)
		if expiry == "" {
			continue
		}

		strikePrice, err := strconv.ParseFloat(strikePriceStr, 64)
		if err != nil {
			continue
		}

		key := buildScripKey(underlying, expiry, strikePrice, optType)
		sm.index[key] = secID
		rowCount++
	}

	log.Printf("[SCRIP] Loaded %d OPTIDX entries from scrip master", rowCount)
	return sm, nil
}

// FindOptionSecurityID returns the Dhan security_id for a specific option contract.
// indexName: NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY
// expiryDate: YYYY-MM-DD
// strike: strike price as float64
// optType: "CE" or "PE"
func (sm *ScripMaster) FindOptionSecurityID(indexName, expiryDate string, strike float64, optType string) (string, bool) {
	key := buildScripKey(strings.ToUpper(indexName), expiryDate, strike, strings.ToUpper(optType))
	id, ok := sm.index[key]
	return id, ok
}

// ATMStrikesForIndex returns ATM-count...ATM+count strikes for a given spot price.
// e.g. spotPrice=24500, strikeInterval=50, count=5 -> [24250, 24300, ..., 24750]
func ATMStrikesForIndex(spotPrice float64, strikeInterval int, count int) []float64 {
	interval := float64(strikeInterval)
	atm := math.Round(spotPrice/interval) * interval
	strikes := make([]float64, 0, count*2+1)
	for i := -count; i <= count; i++ {
		strikes = append(strikes, atm+float64(i)*interval)
	}
	return strikes
}

// StrikeIntervalForIndex returns the strike step size for a given index name.
func StrikeIntervalForIndex(indexName string) int {
	switch strings.ToUpper(indexName) {
	case "BANKNIFTY":
		return 100
	case "MIDCPNIFTY":
		return 25
	default: // NIFTY, FINNIFTY
		return 50
	}
}

func buildScripKey(index, expiry string, strike float64, optType string) string {
	return fmt.Sprintf("%s|%s|%.0f|%s", index, expiry, strike, optType)
}

// normaliseScripDate converts Dhan scrip master date formats to YYYY-MM-DD.
// Dhan uses "24-Oct-2024" or "2024-10-24".
func normaliseScripDate(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	// Already YYYY-MM-DD
	if len(raw) == 10 && raw[4] == '-' && raw[7] == '-' {
		return raw
	}
	formats := []string{"02-Jan-2006", "02-Jan-06", "2/1/2006", "01/02/2006", "2006-01-02"}
	for _, f := range formats {
		if t, err := time.Parse(f, raw); err == nil {
			return t.Format("2006-01-02")
		}
	}
	return ""
}
