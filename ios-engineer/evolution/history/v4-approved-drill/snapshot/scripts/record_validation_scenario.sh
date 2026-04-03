#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 6 ]; then
  echo "Usage: bash scripts/record_validation_scenario.sh <proposal-file> <scenario> <result> <hits> <deviations> <improvements>"
  echo 'Example: bash scripts/record_validation_scenario.sh evolution/proposals/20260403-fix.md layout pass "命中根因四段式;先看复用链路" "无" "无"'
  exit 1
fi

proposal_file="$1"
scenario="$2"
result="$3"
hits_raw="$4"
deviations_raw="$5"
improvements_raw="$6"

case "$result" in
  pass|partial|fail)
    ;;
  *)
    echo "Unsupported result: ${result}"
    exit 1
    ;;
esac

proposal_id="$(basename "$proposal_file" .md)"
record_file="evolution/validations/${proposal_id}.json"

if [ ! -f "$record_file" ]; then
  echo "Missing validation record: ${record_file}"
  exit 1
fi

ruby -rjson - "$record_file" "$scenario" "$result" "$hits_raw" "$deviations_raw" "$improvements_raw" <<'RUBY'
record_file, scenario, result, hits_raw, deviations_raw, improvements_raw = ARGV

def split_items(text)
  text.split(";").map(&:strip).reject(&:empty?)
end

data = JSON.parse(File.read(record_file))
records = data["scenario_records"] || []

entry = {
  "scenario" => scenario,
  "result" => result,
  "hits" => split_items(hits_raw),
  "deviations" => split_items(deviations_raw),
  "improvements" => split_items(improvements_raw)
}

idx = records.find_index { |item| item["scenario"] == scenario }
if idx
  records[idx] = entry
else
  records << entry
end

results = records.map { |item| item["result"] }
status =
  if records.empty?
    "not_run"
  elsif results.any? { |item| item == "pending" }
    "pending"
  elsif results.any? { |item| item == "fail" }
    "failed"
  elsif results.any? { |item| item == "partial" }
    "partial"
  else
    "passed"
  end

data["scenario_records"] = records
data["scenario_validation_status"] = status
data["promotion_readiness"] =
  if status == "passed" && data["status"] == "validated"
    "ready_to_promote"
  else
    "not_ready"
  end
data["updated_at"] = Time.now.strftime("%Y-%m-%dT%H:%M:%S%z")

File.write(record_file, JSON.pretty_generate(data) + "\n")
RUBY

bash scripts/update_skill_proposal_status.sh "$proposal_file" "$(ruby -rjson -e 'data = JSON.parse(File.read(ARGV[0])); print(data["promotion_readiness"] == "ready_to_promote" ? "ready_to_promote" : data["status"])' "$record_file")" >/dev/null
cat "$record_file"
