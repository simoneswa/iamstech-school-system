#!/bin/sh
echo "Starting IAMSTECH Production Deployment Sequence..."

# Give Railway network 3 seconds to stabilize before connecting to DB
sleep 3

# Run migrations (non-fatal: if DB not ready, app still starts)
echo "Running Database Migration (migrate_v6.py)..."
python3 migrate_v6.py || echo "WARNING: migrate_v6.py failed (non-fatal, app will handle at runtime)"

echo "Running Database Migration (migrate_v7_otp.py)..."
python3 migrate_v7_otp.py || echo "WARNING: migrate_v7_otp.py failed (non-fatal)"

# Seed SuperAdmin if missing
echo "Ensuring SuperAdmin account..."
python3 seed_sa.py || echo "WARNING: seed_sa.py failed (non-fatal)"

touch /tmp/migration_success
echo "Migration sequence complete. Starting Gunicorn..."

# Start production server — always runs regardless of migration results
exec gunicorn app:app \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 2 \
    --timeout 120 \
    --log-file - \
    --access-logfile - \
    --error-logfile - \
    --log-level info
