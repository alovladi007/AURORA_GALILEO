#!/bin/bash
# Let's Encrypt SSL Certificate Setup for GALILEO Platform
# Automated certificate provisioning and renewal

set -e

# Configuration
DOMAIN="${DOMAIN:-galileo.example.com}"
EMAIL="${LETSENCRYPT_EMAIL:-admin@example.com}"
STAGING="${LETSENCRYPT_STAGING:-0}"
CERT_DIR="/etc/nginx/ssl"
WEBROOT="/var/www/certbot"

echo "=========================================="
echo "Let's Encrypt Certificate Setup"
echo "Domain: ${DOMAIN}"
echo "Email: ${EMAIL}"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

# Create directories
mkdir -p "${CERT_DIR}"
mkdir -p "${WEBROOT}"

# Install certbot if not present
if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    if [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        apt-get update
        apt-get install -y certbot
    elif [ -f /etc/redhat-release ]; then
        # RHEL/CentOS
        yum install -y certbot
    else
        echo "Error: Unsupported OS. Please install certbot manually."
        exit 1
    fi
fi

# Determine staging flag
STAGING_FLAG=""
if [ "${STAGING}" = "1" ]; then
    echo "Using Let's Encrypt staging environment (test certificates)"
    STAGING_FLAG="--staging"
fi

# Stop nginx if running (certbot standalone mode)
if systemctl is-active --quiet nginx; then
    echo "Stopping nginx for certificate issuance..."
    systemctl stop nginx
    RESTART_NGINX=1
else
    RESTART_NGINX=0
fi

# Request certificate
echo "Requesting certificate for ${DOMAIN}..."
certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "${EMAIL}" \
    --domains "${DOMAIN}" \
    ${STAGING_FLAG} \
    --cert-name galileo

# Copy certificates to nginx directory
if [ -d "/etc/letsencrypt/live/galileo" ]; then
    echo "Copying certificates to ${CERT_DIR}..."
    cp /etc/letsencrypt/live/galileo/fullchain.pem "${CERT_DIR}/"
    cp /etc/letsencrypt/live/galileo/privkey.pem "${CERT_DIR}/"
    cp /etc/letsencrypt/live/galileo/chain.pem "${CERT_DIR}/"

    # Set permissions
    chmod 644 "${CERT_DIR}/fullchain.pem"
    chmod 644 "${CERT_DIR}/chain.pem"
    chmod 600 "${CERT_DIR}/privkey.pem"

    echo "✓ Certificates installed successfully"
else
    echo "✗ Certificate issuance failed"
    exit 1
fi

# Setup automatic renewal with systemd timer
echo "Setting up automatic certificate renewal..."

# Create renewal script
cat > /usr/local/bin/renew-galileo-certs.sh <<'RENEWAL_SCRIPT'
#!/bin/bash
# Automatic certificate renewal for GALILEO

set -e

echo "Renewing Let's Encrypt certificates..."
certbot renew --quiet --deploy-hook "systemctl reload nginx"

# Copy renewed certificates
CERT_DIR="/etc/nginx/ssl"
if [ -d "/etc/letsencrypt/live/galileo" ]; then
    cp /etc/letsencrypt/live/galileo/fullchain.pem "${CERT_DIR}/"
    cp /etc/letsencrypt/live/galileo/privkey.pem "${CERT_DIR}/"
    cp /etc/letsencrypt/live/galileo/chain.pem "${CERT_DIR}/"

    chmod 644 "${CERT_DIR}/fullchain.pem"
    chmod 644 "${CERT_DIR}/chain.pem"
    chmod 600 "${CERT_DIR}/privkey.pem"

    echo "✓ Certificates renewed and copied"
fi
RENEWAL_SCRIPT

chmod +x /usr/local/bin/renew-galileo-certs.sh

# Create systemd service
cat > /etc/systemd/system/galileo-cert-renew.service <<'SERVICE'
[Unit]
Description=Renew GALILEO Let's Encrypt certificates
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/renew-galileo-certs.sh
SERVICE

# Create systemd timer (runs twice daily)
cat > /etc/systemd/system/galileo-cert-renew.timer <<'TIMER'
[Unit]
Description=Renew GALILEO Let's Encrypt certificates twice daily
After=network.target

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
TIMER

# Enable and start timer
systemctl daemon-reload
systemctl enable galileo-cert-renew.timer
systemctl start galileo-cert-renew.timer

echo "✓ Automatic renewal configured (runs twice daily)"

# Test renewal (dry-run)
echo "Testing certificate renewal..."
certbot renew --dry-run

# Restart nginx if it was running
if [ "${RESTART_NGINX}" = "1" ]; then
    echo "Starting nginx..."
    systemctl start nginx
fi

# Display certificate info
echo ""
echo "=========================================="
echo "Certificate Information"
echo "=========================================="
openssl x509 -in "${CERT_DIR}/fullchain.pem" -noout -text | grep -A 2 "Validity"
openssl x509 -in "${CERT_DIR}/fullchain.pem" -noout -text | grep "Subject:"
openssl x509 -in "${CERT_DIR}/fullchain.pem" -noout -text | grep "DNS:"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo "Certificates installed in: ${CERT_DIR}"
echo "Automatic renewal: Twice daily via systemd timer"
echo "Test renewal: certbot renew --dry-run"
echo "Force renewal: certbot renew --force-renewal"
echo ""
echo "Next steps:"
echo "1. Update nginx configuration with your domain name"
echo "2. Uncomment HSTS header in nginx config after testing"
echo "3. Test HTTPS: https://${DOMAIN}"
echo "4. Check SSL rating: https://www.ssllabs.com/ssltest/"
echo "=========================================="

exit 0
