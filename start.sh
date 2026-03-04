#!/usr/bin/env bash
# Start the Samaritan web interface (HTTPS on port 8800)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── TLS cert (required for Web Speech API on all browsers) ───
CERT_DIR="$SCRIPT_DIR/certs"
CERT="$CERT_DIR/cert.pem"
KEY="$CERT_DIR/key.pem"

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
  echo "[samaritan] Generating self-signed TLS certificate..."
  mkdir -p "$CERT_DIR"
  LOCAL_IP=$(hostname -I | awk '{print $1}')
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY" \
    -out "$CERT" \
    -days 3650 \
    -subj "/CN=samaritan.local" \
    -addext "subjectAltName=IP:${LOCAL_IP},IP:127.0.0.1,DNS:localhost" \
    2>/dev/null
  echo "[samaritan] Certificate generated for IP: $LOCAL_IP"
  echo "[samaritan] You will need to accept the browser security warning once."
fi

# ── Python venv ───────────────────────────────────────────────
if [ ! -d "venv" ]; then
  echo "[samaritan] Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         SAMARITAN INTERFACE ONLINE           ║"
echo "  ╠══════════════════════════════════════════════╣"
echo "  ║  https://${LOCAL_IP}:8800                    "
echo "  ║  https://localhost:8800                      "
echo "  ║                                              ║"
echo "  ║  NOTE: Accept the self-signed cert warning   ║"
echo "  ║  in your browser on first visit.             ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

python samaritan.py >> samaritan.log 2>&1 &
