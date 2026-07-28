#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

echo "Waiting for PostgreSQL to start..."

# Wait until Postgres is available on port 5432
while ! nc -z $DB_HOST $DB_PORT; do
  sleep 0.1
done

echo "PostgreSQL started successfully!"

# Create new migration files for schema changes
echo "Making database migrations..."
python manage.py makemigrations --noinput

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Run custom management command to check & create initial admin
echo "Checking/Creating Superuser..."
python manage.py initadmin

# Execute the container's main process (passed from Dockerfile CMD or docker-compose)
exec "$@"