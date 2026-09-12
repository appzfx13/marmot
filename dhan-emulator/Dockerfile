# Multi-stage Docker build for DHAN-EMULATOR
FROM golang:1.23-alpine AS builder

WORKDIR /build

# Copy dependency definition
COPY go.mod ./
RUN go mod download || true

# Copy source code
COPY . .
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o dhan-emulator main.go

# Production minimal runtime
FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# Copy binary and dashboard template
COPY --from=builder /build/dhan-emulator /usr/local/bin/dhan-emulator
COPY --from=builder /build/templates /app/templates

EXPOSE 8088

CMD ["/usr/local/bin/dhan-emulator"]
