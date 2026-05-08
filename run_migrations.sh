#!/bin/sh
set -e
echo "Starting IAMSTECH Production Deployment Sequence..."


# Run the core repair and migration script
echo "Running Database Migration & Repair (migrate_v6.py)..."
python3 migrate_v6.py
echo "Running Database Migration & Repair (migrate_v7_otp.py)..."
python3 migrate_v7_otp.py

# Seed SuperAdmin if missing
echo "Ensuring SuperAdmin account..."
python3 seed_sa.py



# Final checks completed, mark as success
touch /tmp/migration_success
echo "Migration sequence successful."

# Final checks completed, start the server
echo "Starting Gunicorn server..."
exec gunicorn app:app --log-file - --access-logfile - --error-logfile - --log-level info
