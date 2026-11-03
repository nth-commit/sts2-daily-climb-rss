#!/bin/sh
# Installs a launchd agent that starts the feed workflow at 10:00 local time.
#   scripts/install-launchd.sh             install or reinstall
#   scripts/install-launchd.sh --uninstall remove the agent
# Re-run after moving the repository folder.
set -eu

label="io.github.nth-commit.sts2-daily-climb"
plist="$HOME/Library/LaunchAgents/$label.plist"
log="$HOME/Library/Logs/sts2-daily-climb.log"
domain="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "$domain/$label" 2>/dev/null || true
  rm -f "$plist"
  echo "Removed $label"
  exit 0
fi

[ "$(uname)" = "Darwin" ] || { echo "This script is for macOS (launchd)." >&2; exit 1; }

gh_bin="$(command -v gh || true)"
[ -n "$gh_bin" ] || { echo "Install the GitHub CLI first: brew install gh" >&2; exit 1; }
"$gh_bin" auth status >/dev/null 2>&1 || { echo "Log in to the GitHub CLI first: gh auth login" >&2; exit 1; }

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo="$(cd "$repo_dir" && "$gh_bin" repo view --json nameWithOwner -q .nameWithOwner)"
trigger="$repo_dir/scripts/trigger-workflow.sh"
chmod +x "$trigger"

mkdir -p "$(dirname "$plist")" "$(dirname "$log")"
cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$trigger</string>
    <string>$repo</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>$(dirname "$gh_bin"):/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>10</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$log</string>
  <key>StandardErrorPath</key>
  <string>$log</string>
</dict>
</plist>
EOF
plutil -lint "$plist" >/dev/null

launchctl bootout "$domain/$label" 2>/dev/null || true
launchctl bootstrap "$domain" "$plist"

echo "Installed $label: starts the $repo workflow daily at 10:00 local time."
echo "Log: $log"
echo "Run it now: launchctl kickstart $domain/$label"
