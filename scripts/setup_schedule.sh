#!/usr/bin/env bash
# Setup systemd timer for scheduled NSDN runs.
# Generates service + timer unit files and prints install commands.
#
# Usage:
#   bash scripts/setup_schedule.sh [--user]
#
#   --user   Install to ~/.config/systemd/user/ (no sudo needed)
#            Without --user, installs to /etc/systemd/system/ (requires sudo)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
INSTALL_USER=false
if [[ "${1:-}" == "--user" ]]; then
    INSTALL_USER=true
fi

# Detect poetry (use absolute path for systemd compatibility)
if command -v poetry &>/dev/null; then
    POETRY_CMD="$(command -v poetry)"
else
    echo "Error: poetry not found in PATH" >&2
    exit 1
fi

# Detect .env
ENV_FILE="$PROJECT_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Warning: .env not found at $ENV_FILE" >&2
    echo "Delivery credentials (Telegram, email) require .env with TELEGRAM_* vars." >&2
fi

# Build schedule from config (fallback to defaults)
# We read the YAML directly to get actual schedule times
SCHEDULE_TIMES="08:00,13:00,19:00"
if command -v python3 &>/dev/null; then
    DETECTED=$(python3 -c "
import yaml, sys
try:
    with open('$PROJECT_ROOT/config/nsdn.yaml') as f:
        data = yaml.safe_load(f) or {}
    times = data.get('schedule', ['08:00', '13:00', '19:00'])
    print(','.join(times))
except:
    print('08:00,13:00,19:00')
" 2>/dev/null || echo "08:00,13:00,19:00")
    SCHEDULE_TIMES="$DETECTED"
fi

# Convert comma-separated times to systemd OnCalendar format
# "08:00,13:00,19:00" -> "OnCalendar=*-*-* 08:00:00\nOnCalendar=*-*-* 13:00:00\nOnCalendar=*-*-* 19:00:00"
ON_CALENDAR_LINES=""
IFS=',' read -ra TIMES <<< "$SCHEDULE_TIMES"
for t in "${TIMES[@]}"; do
    ON_CALENDAR_LINES+="OnCalendar=*-*-* ${t}:00"$'\n'
done

# Choose install directory
if $INSTALL_USER; then
    UNIT_DIR="$HOME/.config/systemd/user"
    PREFIX=""
    SUDO=""
else
    UNIT_DIR="/etc/systemd/system"
    PREFIX=""
    SUDO="sudo"
fi

mkdir -p "$UNIT_DIR"

# Generate service file
SERVICE_FILE="$UNIT_DIR/nsdn.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=NSDN — No Social Detox News (scheduled run)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$POETRY_CMD run nsdn run --deliver
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Generate timer file
TIMER_FILE="$UNIT_DIR/nsdn.timer"
cat > "$TIMER_FILE" <<EOF
[Unit]
Description=NSDN — Run pipeline at scheduled times

[Timer]
${ON_CALENDAR_LINES}
Persistent=true

[Install]
WantedBy=timers.target
EOF

echo "=== NSDN Schedule Setup ==="
echo ""
echo "Generated files:"
echo "  Service: $SERVICE_FILE"
echo "  Timer:   $TIMER_FILE"
echo ""
echo "Schedule times: $SCHEDULE_TIMES"
echo "Environment:    $ENV_FILE"
echo ""
echo "To activate, run:"
echo ""
if $INSTALL_USER; then
    echo "  systemctl --user daemon-reload"
    echo "  systemctl --user enable --now nsdn.timer"
    echo ""
    echo "  # Check status:"
    echo "  systemctl --user status nsdn.timer"
    echo "  # View logs:"
    echo "  journalctl --user -u nsdn.service"
else
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable --now nsdn.timer"
    echo ""
    echo "  # Check status:"
    echo "  sudo systemctl status nsdn.timer"
    echo "  # View logs:"
    echo "  sudo journalctl -u nsdn.service"
fi
echo ""
echo "To run manually (test):"
echo "  cd $PROJECT_ROOT && $POETRY_CMD run nsdn run --deliver"
echo ""
echo "To stop:"
if $INSTALL_USER; then
    echo "  systemctl --user disable --now nsdn.timer"
else
    echo "  sudo systemctl disable --now nsdn.timer"
fi
