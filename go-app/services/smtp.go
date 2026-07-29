package services

import (
	"fmt"
	"net/smtp"
	"os"
	"strings"
)

type EmailService struct {
	smtpHost string
	smtpPort string
	from     string
	password string
}

// NewEmailService initializes the SMTP email service configuration from environment variables
func NewEmailService() *EmailService {
	return &EmailService{
		smtpHost: os.Getenv("SMTP_HOST"),     // e.g., "smtp.gmail.com" or "smtp.mailtrap.io"
		smtpPort: os.Getenv("SMTP_PORT"),     // e.g., "587"
		from:     os.Getenv("SMTP_FROM_EMAIL"), // e.g., "noreply@yourdomain.com"
		password: os.Getenv("SMTP_PASSWORD"), // App Password or SMTP API Key
	}
}

// SendEmail sends a plain-text email to the specified recipient
func (s *EmailService) SendEmail(toEmail, subject, body string) error {
	addr := fmt.Sprintf("%s:%s", s.smtpHost, s.smtpPort)

	// Set up SMTP Authentication
	auth := smtp.PlainAuth("", s.from, s.password, s.smtpHost)

	// Build MIME Header + Email Body
	headers := make(map[string]string)
	headers["From"] = s.from
	headers["To"] = toEmail
	headers["Subject"] = subject
	headers["MIME-Version"] = "1.0"
	headers["Content-Type"] = "text/plain; charset=\"utf-8\""

	var message strings.Builder
	for k, v := range headers {
		message.WriteString(fmt.Sprintf("%s: %s\r\n", k, v))
	}
	message.WriteString("\r\n" + body)

	// Send Email via SMTP
	err := smtp.SendMail(addr, auth, s.from, []string{toEmail}, []byte(message.String()))
	if err != nil {
		return fmt.Errorf("smtp email delivery error: %w", err)
	}

	return nil
}

// SendOTP handles sending an OTP specifically via Email
func (s *EmailService) SendOTP(toEmail, otpCode string) error {
	subject := "Your Security Verification Code"
	body := fmt.Sprintf("Your OTP code is: %s. It will expire in 5 minutes.", otpCode)
	return s.SendEmail(toEmail, subject, body)
}