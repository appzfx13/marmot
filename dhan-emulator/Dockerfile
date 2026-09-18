FROM golang:1.25-bookworm AS builder

ENV GOTOOLCHAIN=auto

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency definition
COPY go.mod ./
RUN go mod download || true

# Copy source code
COPY . .
RUN go mod tidy
RUN CGO_ENABLED=1 GOOS=linux go build -ldflags="-w -s" -o dhan-emulator main.go

# Production minimal runtime
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary and dashboard template
COPY --from=builder /build/dhan-emulator /usr/local/bin/dhan-emulator
COPY --from=builder /build/templates /app/templates

EXPOSE 8088

CMD ["/usr/local/bin/dhan-emulator"]
