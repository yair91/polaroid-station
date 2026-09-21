#!/bin/bash
# user_data de la instancia EC2. Los marcadores __VAR__ los reemplaza setup.sh.
set -xeuo pipefail
exec > >(tee /var/log/polaroid-bootstrap.log) 2>&1

dnf update -y
dnf install -y git python3.11 python3.11-pip mariadb105 dejavu-sans-fonts

APP_DIR=/opt/polaroid
rm -rf "$APP_DIR"
git clone --branch "__REPO_BRANCH__" --depth 1 "__REPO_URL__" "$APP_DIR"

python3.11 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# Configuracion NO sensible. Las credenciales de RDS se leen en runtime
# desde Secrets Manager usando el instance profile de la instancia.
cat > /etc/polaroid.env <<EOF
AWS_REGION=__AWS_REGION__
S3_BUCKET=__BUCKET_NAME__
RDS_SECRET_NAME=__SECRET_NAME__
DB_NAME=__DB_NAME__
EOF
chmod 600 /etc/polaroid.env

id -u polaroid &>/dev/null || useradd --system --home "$APP_DIR" --shell /sbin/nologin polaroid
chown -R polaroid:polaroid "$APP_DIR"

cat > /etc/systemd/system/polaroid.service <<EOF
[Unit]
Description=Estacion de fotos Polaroid (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=polaroid
WorkingDirectory=$APP_DIR
EnvironmentFile=/etc/polaroid.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port __APP_PORT__
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now polaroid.service
