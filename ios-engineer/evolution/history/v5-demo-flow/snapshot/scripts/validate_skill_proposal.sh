#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/validate_skill_proposal.sh <proposal-file> [scenario-slug ...]"
  echo "Example: bash scripts/validate_skill_proposal.sh evolution/proposals/20260403-fix.md layout parameter-pass-through"
  exit 1
fi

proposal_file="$1"
shift || true

if [ ! -f "$proposal_file" ]; then
  echo "Missing proposal file: ${proposal_file}"
  exit 1
fi

proposal_id="$(basename "$proposal_file" .md)"
timestamp="$(date '+%Y-%m-%dT%H:%M:%S%z')"
record_file="evolution/validations/${proposal_id}.json"
tmp_output="$(mktemp)"

set +e
bash scripts/validate_skill_evolution.sh >"$tmp_output" 2>&1
exit_code=$?
set -e

scenario_status="not_run"
scenario_records='[]'

if [ "$#" -gt 0 ]; then
  scenario_status="pending"
  scenario_records="$(printf '%s\n' "$@" | ruby -rjson -e 'items = STDIN.read.lines.map(&:strip).reject(&:empty?).map { |slug| {"scenario" => slug, "result" => "pending", "hits" => [], "deviations" => [], "improvements" => []} }; print JSON.generate(items)')"
fi

if [ "$exit_code" -eq 0 ]; then
  status="validated"
else
  status="rejected"
fi

escaped_output="$(ruby -rjson -e 'print JSON.dump(ARGF.read)' "$tmp_output")"

cat > "$record_file" <<EOF
{
  "proposal_id": "${proposal_id}",
  "proposal_file": "${proposal_file}",
  "validated_at": "${timestamp}",
  "status": "${status}",
  "exit_code": ${exit_code},
  "active_version": "$(ruby -rjson -e 'print JSON.parse(File.read("evolution/active_version.json"))["active_version"]')",
  "base_validation_output": ${escaped_output},
  "promotion_readiness": "not_ready",
  "scenario_validation_status": "${scenario_status}",
  "scenario_records": ${scenario_records}
}
EOF

rm -f "$tmp_output"

bash scripts/update_skill_proposal_status.sh "$proposal_file" "$status" >/dev/null
cat "$record_file"

if [ "$exit_code" -ne 0 ]; then
  exit "$exit_code"
fi
