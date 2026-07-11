#!/bin/bash
set -euo pipefail
APP_DIR=/opt/kitchens-bot
cd "$APP_DIR"
.venv/bin/pip install -q -r requirements.txt

mkdir -p /opt/kitchens-bot/uploads/catalog

cat > /etc/systemd/system/kitchens-admin.service <<'EOF'
[Unit]
Description=Kitchens Admin Web Dashboard
After=network-online.target docker.service kitchens-bot.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/kitchens-bot
EnvironmentFile=/opt/kitchens-bot/.env
ExecStart=/opt/kitchens-bot/.venv/bin/python -m src.admin_web.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

if command -v nginx >/dev/null 2>&1; then
  cat > /etc/nginx/sites-available/kitchen.alexklyvibe.ru <<'EOF'
server {
    listen 80;
    server_name kitchen.alexklyvibe.ru;

    client_max_body_size 12M;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
  ln -sf /etc/nginx/sites-available/kitchen.alexklyvibe.ru /etc/nginx/sites-enabled/kitchen.alexklyvibe.ru
  nginx -t
  systemctl reload nginx
fi

systemctl daemon-reload
systemctl enable kitchens-admin.service
systemctl restart kitchens-admin.service
sleep 2
systemctl is-active kitchens-admin.service
