package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/riverqueue/river"
	"github.com/riverqueue/river/riverdriver/riverpgxv5"
	"github.com/riverqueue/river/rivermigrate"

	"go-app/services"
	"go-app/workers"
)

func main() {
	// Root context listening for interrupt / termination signals
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	// 1. Initialize External Services
	smsService := services.NewSMSService()
	notifierService := services.NewNotifierService()
	// Note: If you add Email/Notifier services, initialize them here 
	// and add them to the SendOTPWorker struct below.

	// 2. Build Database Connection URL
	dbURL := fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
		os.Getenv("DB_USER"),
		os.Getenv("DB_PASSWORD"),
		os.Getenv("DB_HOST"),
		os.Getenv("DB_PORT"),
		os.Getenv("DB_NAME"),
	)

	// 3. Connect to PostgreSQL Pool
	dbPool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		log.Fatalf("Unable to connect to database: %v", err)
	}
	defer dbPool.Close()

	// 4. Run River Database Migrations
	migrator, err := rivermigrate.New[pgx.Tx](riverpgxv5.New(dbPool), nil)
	if err != nil {
		log.Fatalf("Error creating migrator: %v", err)
	}

	_, err = migrator.Migrate(ctx, rivermigrate.DirectionUp, &rivermigrate.MigrateOpts{})
	if err != nil {
		log.Fatalf("Error running River migrations: %v", err)
	}
	log.Println("River database migrations applied successfully!")

	// 5. Register Workers
	workersMap := river.NewWorkers()
	river.AddWorker(workersMap, &workers.SendOTPWorker{
		SMSService: smsService,
		// If you have EmailService or NotifierService, add them here
	})

	// 6. Initialize River Client
	riverClient, err := river.NewClient(riverpgxv5.New(dbPool), &river.Config{
		Queues: map[string]river.QueueConfig{
			river.QueueDefault: {MaxWorkers: 50},
		},
		Workers: workersMap,
	})
	if err != nil {
		log.Fatalf("Error initializing River client: %v", err)
	}

	// 7. Start River Worker Engine
	if err := riverClient.Start(ctx); err != nil {
		log.Fatalf("Error starting River client: %v", err)
	}
	log.Println("River background worker started...")

	// Ensure River client stops gracefully when context cancels
	defer func() {
		stopCtx, stopCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer stopCancel()
		if err := riverClient.Stop(stopCtx); err != nil {
			log.Printf("Error shutting down River client: %v", err)
		} else {
			log.Println("River worker shut down cleanly.")
		}
	}()

	// 8. Health Check HTTP Server
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "Go service and River worker are running successfully!")
	})

	server := &http.Server{
		Addr:    ":8081",
		Handler: mux,
	}

	go func() {
		log.Println("Go app listening on port 8081...")
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	// Wait for OS shutdown signal
	<-ctx.Done()
	log.Println("Shutdown signal received, exiting gracefully...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("HTTP server Shutdown error: %v", err)
	}
}