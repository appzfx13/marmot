#!/bin/sh
set -e

# Ensure variables are set, or provide safe defaults ---
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."

# Use a robust loop to prevent infinite hangs if DB fails ---
count=0
until nc -z "$DB_HOST" "$DB_PORT" || [ $count -eq 60 ]; do
  echo "Postgres is unavailable - sleeping (attempt $count/60)"
  sleep 1
  count=$((count+1))
done

if [ $count -eq 60 ]; then
  echo "Error: Could not connect to PostgreSQL at $DB_HOST:$DB_PORT"
  exit 1
fi

echo "PostgreSQL started successfully!"

# --- Migrations ---
echo "Making migrations for core and dependent apps..."
python manage.py makemigrations users common admins api market masters notifications trade_config trade_core --noinput
python manage.py makemigrations --noinput

echo "Applying database migrations..."
python manage.py migrate --noinput

# --- Static Files ---
echo "Collecting static files..."
python manage.py collectstatic --noinput

# --- Setup Admin & Dummy Data ---
echo "Checking/Creating Superuser and Sample Users..."
python manage.py initadmin

echo "Seeding/Verifying Backtest Strategy Rules..."
python manage.py seed_backtest_rules

# Execute main container process
exec "$@"