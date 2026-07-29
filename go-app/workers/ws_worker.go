package workers

import (
	"context"
	"fmt"
	"go-app/services"

	"github.com/riverqueue/river"
)

// SendWSNotificationArgs defines the job payload for sending a WebSocket event.
type SendWSNotificationArgs struct {
	Topic     string                 `json:"topic"`
	EventType string                 `json:"event_type"`
	Status    string                 `json:"status"`
	Message   string                 `json:"message"`
	Data      map[string]interface{} `json:"data"`
}

func (SendWSNotificationArgs) Kind() string { return "send_ws_notification" }

// WSNotificationWorker processes WebSocket notification dispatches.
type WSNotificationWorker struct {
	river.WorkerDefaults[SendWSNotificationArgs]
	NotifierService *services.NotifierService
}

func (w *WSNotificationWorker) Work(ctx context.Context, job *river.Job[SendWSNotificationArgs]) error {
	if w.NotifierService == nil {
		return fmt.Errorf("NotifierService is not initialized")
	}

	err := w.NotifierService.PublishEvent(ctx, services.SystemEvent{
		Topic:     job.Args.Topic,
		EventType: job.Args.EventType,
		Status:    job.Args.Status,
		Message:   job.Args.Message,
		Data:      job.Args.Data,
	})

	if err != nil {
		return fmt.Errorf("failed to publish websocket event: %w", err)
	}

	return nil
}