#!/bin/sh
# Database Backup Script for GALILEO Platform
# Performs automated PostgreSQL backups with compression and retention management

set -e

# Configuration
BACKUP_DIR="/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/galileo_backup_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

echo "=========================================="
echo "GALILEO Database Backup"
echo "Started at: $(date)"
echo "=========================================="

# Perform database backup with compression
echo "Creating backup: ${BACKUP_FILE}"
pg_dump -h ${PGHOST} -p ${PGPORT} -U ${PGUSER} -d ${PGDATABASE} \
    --format=plain \
    --no-owner \
    --no-acl \
    --compress=0 \
    | gzip > "${BACKUP_FILE}"

# Verify backup was created successfully
if [ -f "${BACKUP_FILE}" ]; then
    BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "✓ Backup created successfully: ${BACKUP_FILE} (${BACKUP_SIZE})"
else
    echo "✗ Backup failed: ${BACKUP_FILE} not found"
    exit 1
fi

# Clean up old backups (keep only last N days)
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "galileo_backup_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete

# Count remaining backups
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "galileo_backup_*.sql.gz" -type f | wc -l)
echo "✓ Retention cleanup complete. Total backups: ${BACKUP_COUNT}"

# Calculate total backup size
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
echo "Total backup storage used: ${TOTAL_SIZE}"

echo "=========================================="
echo "Backup completed at: $(date)"
echo "=========================================="

# Optional: Upload to S3 if configured
if [ -n "${AWS_ACCESS_KEY_ID}" ] && [ -n "${AWS_SECRET_ACCESS_KEY}" ] && [ -n "${S3_BACKUP_BUCKET}" ]; then
    echo "Uploading backup to S3: ${S3_BACKUP_BUCKET}"
    # Requires aws-cli to be installed in the container
    # aws s3 cp "${BACKUP_FILE}" "s3://${S3_BACKUP_BUCKET}/galileo-backups/"
    # echo "✓ Backup uploaded to S3"
fi

exit 0
