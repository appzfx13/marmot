package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go-app/config"
	"go-app/services"
	"go-app/workers"
	"go-app/ws"
)

func main() {
	goLogger := services.GetLogger()
	goLogger.Info("==================================================")
	goLogger.Info("🚀 Starting Marmot Go Market Data Engine...")
	goLogger.Info("==================================================")

	// 1. Setup Context for Graceful Container Shutdowns (SIGINT / SIGTERM)
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// 2. Load Configuration from Environment Variables
	cfg := config.LoadConfig()

	// 3. Connect to Shared PostgreSQL DB (State Layer)
	dbService, err := services.NewDBService(ctx, cfg.DatabaseURL, cfg.DBTableName)
	if err != nil {
		goLogger.Exception(err, "❌ DB Connection Error")
		log.Fatalf("❌ DB Connection Error: %v\n", err)
	}
	defer dbService.Close()

	// 4. Connect to Redis Broker (Pub/Sub IPC Layer)
	redisService, err := services.NewRedisService(ctx, cfg.RedisURL)
	if err != nil {
		goLogger.Exception(err, "❌ Redis Connection Error")
		log.Fatalf("❌ Redis Connection Error: %v\n", err)
	}
	defer redisService.Close()

	// 5. Initialize WebSocket Hub
	hub := ws.NewHub()
	go hub.Run()

	// 6. Initialize Task Manager
	taskManager := workers.NewTaskManager(dbService, cfg, hub)

	// 7. Start Listening for Django IPC Commands on Redis Channel
	redisChannel := "market_backup_commands"
	go taskManager.StartListener(ctx, redisService, redisChannel)

	// 8. Start HTTP Server for WebSockets, TradingView Chart Data API & UDF Protocol
	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		ws.ServeWs(hub, w, r)
	})
	http.HandleFunc("/api/chart", func(w http.ResponseWriter, r *http.Request) {
		services.ServeChartData(dbService, w, r)
	})
	http.HandleFunc("/api/udf/config", services.ServeUDFConfig)
	http.HandleFunc("/api/udf/symbols", services.ServeUDFSymbols)
	http.HandleFunc("/api/udf/history", func(w http.ResponseWriter, r *http.Request) {
		services.ServeUDFHistory(dbService, w, r)
	})
	server := &http.Server{Addr: ":" + cfg.WSPort}
	go func() {
		log.Printf("🌐 Starting WebSocket Server on port %s...", cfg.WSPort)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("❌ HTTP server error: %v", err)
		}
	}()

	log.Println("⚡ Go Engine initialized successfully. Ready to process tasks and WS clients!")

	// 9. Block Main Thread Until Container Shutdown Signal
	<-ctx.Done()
	log.Println("\n🛑 Termination signal received. Cleaning up active tasks and connections...")

	// Provide 5-second window for goroutines to save state before exit
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("HTTP server shutdown error: %v", err)
	}

	log.Println("👋 Marmot Go Engine shutdown complete.")
}