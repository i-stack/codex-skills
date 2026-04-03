#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 2 ]; then
  echo "Usage: bash scripts/promote_skill_evolution.sh <new-version> <source> [proposal-file]"
  echo "Example: bash scripts/promote_skill_evolution.sh v2 proposal:20260403-fix-root-cause evolution/proposals/20260403-fix-root-cause.md"
  exit 1
fi

new_version="$1"
source_ref="$2"
proposal_file="${3:-}"
history_dir="evolution/history/${new_version}"
snapshot_dir="${history_dir}/snapshot"

if [ -e "$history_dir" ]; then
  echo "Version already exists: ${new_version}"
  exit 1
fi

if [ -n "$proposal_file" ]; then
  if [ ! -f "$proposal_file" ]; then
    echo "Missing proposal file: ${proposal_file}"
    exit 1
  fi

  proposal_status="$(ruby - "$proposal_file" <<'RUBY'
proposal_file = ARGV[0]
lines = File.readlines(proposal_file)
status_index = lines.find_index { |line| line.strip == "## 状态" }
abort("Missing status section") unless status_index
value_index = status_index + 1
abort("Missing status value") unless value_index < lines.length
print lines[value_index].sub(/^- /, "").strip
RUBY
)"

  if [ "$proposal_status" != "approved" ]; then
    echo "Proposal is not approved: ${proposal_status}"
    exit 1
  fi

  proposal_id="$(basename "$proposal_file" .md)"
  approval_file="evolution/approvals/${proposal_id}.json"
  if [ ! -f "$approval_file" ]; then
    echo "Missing approval record: ${approval_file}"
    exit 1
  fi
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

if [ -n "$proposal_file" ]; then
  bash scripts/update_skill_proposal_status.sh "$proposal_file" promoted >/dev/null
fi

echo "Promoted ${new_version}"
