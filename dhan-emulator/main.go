package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"dhan-emulator/engine"
	"dhan-emulator/handlers"
	"dhan-emulator/streamer"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8088"
	}

	postbackURL := os.Getenv("MARMOT_POSTBACK_URL")
	if postbackURL == "" {
		postbackURL = "http://web:8000/postback/dhan/postback/"
	}

	backupDir := os.Getenv("PARQUET_DIR")
	if backupDir == "" {
		backupDir = "/app/backup"
	}

	tmplPath := os.Getenv("TEMPLATE_PATH")
	if tmplPath == "" {
		tmplPath = "templates/dashboard.html"
	}

	log.Println("[DHAN-EMULATOR] Initializing Broker Gateway Sandbox...")
	log.Printf("[DHAN-EMULATOR] Postback Target: %s", postbackURL)
	log.Printf("[DHAN-EMULATOR] Parquet Dir: %s", backupDir)

	// 1. Initialize Chaos Engine (Default 20 req/sec)
	chaos := engine.NewChaosManager(20)

	// 2. Initialize In-Memory Matching & Valuation Engine
	matchingEngine := engine.NewMatchingEngine(chaos, postbackURL)

	// 3. Initialize Parquet & Market Feed Streamer
	marketStreamer := streamer.NewParquetStreamer(matchingEngine, backupDir)

	// 4. Initialize HTTP Handler & Routes
	handler, err := handlers.NewHandler(matchingEngine, chaos, marketStreamer, tmplPath)
	if err != nil {
		log.Fatalf("[DHAN-EMULATOR] Failed to initialize handler: %v", err)
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	addr := fmt.Sprintf("0.0.0.0:%s", port)
	log.Printf("[DHAN-EMULATOR] Server listening on %s (Dashboard: http://localhost:%s/mock/dashboard)", addr, port)

	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("[DHAN-EMULATOR] Server failed: %v", err)
	}
}
