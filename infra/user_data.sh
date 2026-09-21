#!/bin/bash

# ---------------------------------------------------------------------------
REPO_URL="https://github.com/yair91/polaroid-station.git"
BUCKET_NAME="polaroid-station-emmanuel-2026"   
SECRET_NAME="polaroid/rds"                      
REGION="us-east-1"
# ---------------------------------------------------------------------------

set -xeuo pipefail
exec > >(tee /var/log/polaroid-bootstrap.log) 2>&1

dnf update -y
dnf install -y git python3.11 python3.11-pip mariadb105 dejavu-sans-fonts

APP_DIR=/opt/polaroid
rm -rf "$APP_DIR"
git clone --depth 1 "$REPO_URL" "$APP_DIR"

python3.11 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# Configuracion NO sensible. La contrasena de RDS se lee en tiempo de ejecucion
# desde Secrets Manager con el instance profile de la instancia.
cat > /etc/polaroid.env <<EOF
AWS_REGION=$REGION
S3_BUCKET=$BUCKET_NAME
RDS_SECRET_NAME=$SECRET_NAME
DB_NAME=polaroids
EOF
chmod 600 /etc/polaroid.env

id -u polaroid &>/dev/null || useradd --system --home "$APP_DIR" --shell /sbin/nologin polaroid
chown -R polaroid:polaroid "$APP_DIR"

cat > /etc/systemd/system/polaroid.service <<'EOF'
[Unit]
Description=Estacion de fotos Polaroid (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=polaroid
WorkingDirectory=/opt/polaroid
EnvironmentFile=/etc/polaroid.env
ExecStart=/opt/polaroid/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now polaroid.service