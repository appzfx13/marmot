FROM golang:1.25-alpine

ENV GOTOOLCHAIN=auto

WORKDIR /app

RUN apk add --no-cache git

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy dependency definition files first
COPY go.mod ./
RUN go mod download

# Copy the rest of the application files
COPY . .

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
CMD ["go", "run", "."]