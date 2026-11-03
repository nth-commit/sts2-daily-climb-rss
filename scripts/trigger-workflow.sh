#!/bin/sh
# Starts the feed workflow on GitHub. launchd runs this at 10:00 local time;
# see install-launchd.sh. Usage: trigger-workflow.sh OWNER/REPO
set -u

repo="$1"
attempts=6

i=1
while [ "$i" -le "$attempts" ]; do
  if gh workflow run daily-feed.yml -R "$repo"; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) started workflow"
    exit 0
  fi
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) attempt $i of $attempts failed"
  [ "$i" -lt "$attempts" ] && sleep 300
  i=$((i + 1))
done
exit 1
