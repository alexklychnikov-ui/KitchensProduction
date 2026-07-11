#!/bin/bash
set -euo pipefail
APP_DIR=/opt/kitchens-bot
cd "$APP_DIR"
.venv/bin/pip install -q -r requirements.txt

cat > /etc/systemd/system/kitchens-bot.service <<'EOF'
[Unit]
Description=Kitchens Production Telegram Bot
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/kitchens-bot
EnvironmentFile=/opt/kitchens-bot/.env
ExecStart=/opt/kitchens-bot/.venv/bin/python -m src.bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable kitchens-bot.service
systemctl restart kitchens-bot.service
sleep 4
systemctl is-active kitchens-bot.service
journalctl -u kitchens-bot.service -n 20 --no-pager
