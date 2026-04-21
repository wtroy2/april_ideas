#!/bin/bash
# Local bootstrap — install deps, run migrations, create superuser if not present.
set -e

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Running migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "✅ Done."
echo "Run: python manage.py runserver"
echo "Run (separate terminal): python manage.py rqworker high default low"
