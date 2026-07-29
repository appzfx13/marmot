package workers

import (
	"context"
	"fmt"
	"go-app/services"

	"github.com/riverqueue/river"
)

type SendOTPArgs struct {
	PhoneNumber string `json:"phone_number,omitempty"`
	Email       string `json:"email,omitempty"`
	OTPCode     string `json:"otp_code"`
}

func (SendOTPArgs) Kind() string { return "send_otp" }

type SendOTPWorker struct {
	river.WorkerDefaults[SendOTPArgs]
	SMSService   *services.SMSService
	EmailService *services.EmailService
	RiverClient  *river.Client[any] // Injected client to insert downstream background jobs
}

func (w *SendOTPWorker) Work(ctx context.Context, job *river.Job[SendOTPArgs]) error {
	phone := job.Args.PhoneNumber
	email := job.Args.Email
	var sendErr error

	// 1. Dispatch via SMS: Only pass phone. Twilio generates the code.
	if phone != "" && w.SMSService != nil {
		if err := w.SMSService.SendOTP(phone); err != nil {
			sendErr = fmt.Errorf("sms error: %w", err)
		}
	}

	// 2. Dispatch via Email: Keep the original signature for email service
	if email != "" && w.EmailService != nil {
		if err := w.EmailService.SendOTP(email, job.Args.OTPCode); err != nil {
			if sendErr != nil {
				sendErr = fmt.Errorf("%v; email error: %w", sendErr, err)
			} else {
				sendErr = fmt.Errorf("email error: %w", err)
			}
		}
	}

	// 3. Enqueue WebSocket Notification Job
	if w.RiverClient != nil {
		status := "SUCCESS"
		msg := fmt.Sprintf("OTP sent successfully to %s", phone)
		if sendErr != nil {
			status = "FAILED"
			msg = fmt.Sprintf("Failed to send OTP to %s: %v", phone, sendErr)
		}

		_, _ = w.RiverClient.Insert(ctx, SendWSNotificationArgs{
			Topic:     "logs_table",
			EventType: "REFRESH_AND_TOAST",
			Status:    status,
			Message:   msg,
			Data:      map[string]interface{}{"phone": phone, "email": email},
		}, nil)
	}

	return sendErr
}