#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 2 ]; then
  echo "Usage: bash scripts/promote_skill_evolution.sh <new-version> <source>"
  echo "Example: bash scripts/promote_skill_evolution.sh v2 proposal:20260403-fix-root-cause"
  exit 1
fi

new_version="$1"
source_ref="$2"
history_dir="evolution/history/${new_version}"
snapshot_dir="${history_dir}/snapshot"

if [ -e "$history_dir" ]; then
  echo "Version already exists: ${new_version}"
  exit 1
fi

bash scripts/validate_skill_evolution.sh

mkdir -p "$snapshot_dir"
cp SKILL.md "${snapshot_dir}/SKILL.md"
cp -R agents "${snapshot_dir}/agents"
cp -R references "${snapshot_dir}/references"
cp -R scripts "${snapshot_dir}/scripts"

cat > "${history_dir}/metadata.json" <<EOF
{
  "version": "${new_version}",
  "promoted_at": "$(date '+%Y-%m-%dT%H:%M:%S%z')",
  "source": "${source_ref}"
}
EOF

cat > evolution/active_version.json <<EOF
{
  "active_version": "${new_version}",
  "status": "active",
  "promoted_at": "$(date '+%Y-%m-%dT%H:%M:%S%z')",
  "source": "${source_ref}",
  "notes": "Promoted after passing base evolution validation."
}
EOF

echo "Promoted ${new_version}"
