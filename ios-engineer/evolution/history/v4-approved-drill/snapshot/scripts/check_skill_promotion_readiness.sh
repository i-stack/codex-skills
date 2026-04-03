#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/check_skill_promotion_readiness.sh <proposal-file>"
  exit 1
fi

proposal_file="$1"

if [ ! -f "$proposal_file" ]; then
  echo "Missing proposal file: ${proposal_file}"
  exit 1
fi

proposal_id="$(basename "$proposal_file" .md)"
record_file="evolution/validations/${proposal_id}.json"
approval_file="evolution/approvals/${proposal_id}.json"

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

approval_status="missing"
if [ -f "$approval_file" ]; then
  approval_status="$(ruby -rjson -e 'print JSON.parse(File.read(ARGV[0]))["status"]' "$approval_file")"
fi

promotion_readiness="unknown"
scenario_status="unknown"
if [ -f "$record_file" ]; then
  readout="$(ruby -rjson -e 'data = JSON.parse(File.read(ARGV[0])); print "#{data["promotion_readiness"]}\n#{data["scenario_validation_status"]}"' "$record_file")"
  promotion_readiness="$(printf '%s' "$readout" | sed -n '1p')"
  scenario_status="$(printf '%s' "$readout" | sed -n '2p')"
fi

cat <<EOF
proposal_status=${proposal_status}
promotion_readiness=${promotion_readiness}
scenario_validation_status=${scenario_status}
approval_status=${approval_status}
EOF

if [ "$proposal_status" = "ready_to_promote" ] && [ "$promotion_readiness" = "ready_to_promote" ] && [ "$approval_status" = "missing" ]; then
  echo "hint=Proposal is ready. To authorize promotion, run: bash scripts/approve_skill_promotion.sh ${proposal_file} \"approved-by-user\""
fi
