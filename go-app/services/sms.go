package services

import (
	"fmt"
	"os"

	"github.com/twilio/twilio-go"
	verify "github.com/twilio/twilio-go/rest/verify/v2"
)

type SMSService struct {
	client     *twilio.RestClient
	serviceSid string
}

// NewSMSService initializes the Twilio client once
func NewSMSService() *SMSService {
	return &SMSService{
		client:     twilio.NewRestClient(),
		serviceSid: os.Getenv("TWILIO_VERIFY_SERVICE_SID"),
	}
}

// SendOTP handles sending the OTP code via Twilio Verify API
func (s *SMSService) SendOTP(toPhone string) error {
	params := &verify.CreateVerificationParams{}
	params.SetTo(toPhone)
	params.SetChannel("sms")

	_, err := s.client.VerifyV2.CreateVerification(s.serviceSid, params)
	if err != nil {
		return fmt.Errorf("twilio delivery error: %w", err)
	}
	return nil
}

// VerifyOTP checks if the OTP code entered by the user is valid
func (s *SMSService) VerifyOTP(toPhone, otpCode string) (bool, error) {
	params := &verify.CreateVerificationCheckParams{}
	params.SetTo(toPhone)
	params.SetCode(otpCode)

	resp, err := s.client.VerifyV2.CreateVerificationCheck(s.serviceSid, params)
	if err != nil {
		return false, fmt.Errorf("twilio verification error: %w", err)
	}

	if resp.Status != nil && *resp.Status == "approved" {
		return true, nil
	}

	return false, nil
}