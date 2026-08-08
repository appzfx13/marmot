FROM golang:1.25-alpine

ENV GOTOOLCHAIN=auto

WORKDIR /app

RUN apk add --no-cache git

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy dependency files first (if go.sum exists locally, it copies it. If not, it just copies go.mod)
COPY go.mod go.sum* ./

# Copy the rest of the application files so 'go mod tidy' can scan them
COPY . .

# Now that the code is here, tidy and download the dependencies
RUN go mod tidy
RUN go mod download

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
CMD ["go", "run", "."] 