#!/bin/sh
set -e

echo "Syncing Go dependencies..."
go mod tidy

echo "Starting Go application..."
exec "$@"