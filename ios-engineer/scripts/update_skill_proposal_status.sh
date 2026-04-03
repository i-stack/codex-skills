#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 2 ]; then
  echo "Usage: bash scripts/update_skill_proposal_status.sh <proposal-file> <status>"
  exit 1
fi

proposal_file="$1"
new_status="$2"

if [ ! -f "$proposal_file" ]; then
  echo "Missing proposal file: ${proposal_file}"
  exit 1
fi

case "$new_status" in
  draft|validated|ready_to_promote|approved|promoted|rejected)
    ;;
  *)
    echo "Unsupported status: ${new_status}"
    exit 1
    ;;
esac

ruby - "$proposal_file" "$new_status" <<'RUBY'
proposal_file = ARGV[0]
new_status = ARGV[1]
lines = File.readlines(proposal_file)
status_index = lines.find_index { |line| line.strip == "## 状态" }
abort("Missing status section") unless status_index
value_index = status_index + 1
abort("Missing status value") unless value_index < lines.length
lines[value_index] = "- #{new_status}\n"
File.write(proposal_file, lines.join)
RUBY

echo "Updated ${proposal_file} -> ${new_status}"
