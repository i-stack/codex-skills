#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/rollback_skill_evolution.sh <version>"
  exit 1
fi

target_version="$1"
history_dir="evolution/history/${target_version}"
snapshot_dir="${history_dir}/snapshot"

if [ ! -d "$snapshot_dir" ]; then
  echo "Missing snapshot for version: ${target_version}"
  exit 1
fi

rm -rf agents references scripts
cp "${snapshot_dir}/SKILL.md" SKILL.md
cp -R "${snapshot_dir}/agents" agents
cp -R "${snapshot_dir}/references" references
cp -R "${snapshot_dir}/scripts" scripts

cat > evolution/active_version.json <<EOF
{
  "active_version": "${target_version}",
  "status": "active",
  "promoted_at": "$(date '+%Y-%m-%dT%H:%M:%S%z')",
  "source": "rollback",
  "notes": "Rolled back to archived stable snapshot."
}
EOF

bash scripts/validate_skill_evolution.sh

echo "Rolled back to ${target_version}"
