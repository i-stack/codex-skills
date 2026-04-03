#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/4] Validate YAML structure"
ruby -e 'require "yaml"; YAML.load_file("SKILL.md"); YAML.load_file("agents/openai.yaml"); puts "YAML OK"'

echo "[2/4] Validate SKILL.md size"
line_count="$(wc -l < SKILL.md | tr -d ' ')"
if [ "$line_count" -gt 500 ]; then
  echo "SKILL.md too long: ${line_count} lines"
  exit 1
fi
echo "SKILL.md lines: ${line_count}"

echo "[3/4] Validate referenced files exist"
missing=0
while IFS= read -r path; do
  [ -z "$path" ] && continue
  if [ ! -f "$path" ]; then
    echo "Missing reference: $path"
    missing=1
  fi
done < <(rg -o 'references/[A-Za-z0-9_./-]+\.md' SKILL.md | sort -u)

if [ "$missing" -ne 0 ]; then
  exit 1
fi
echo "Reference files OK"

echo "[4/4] Validate layering guardrails"
if rg -q '^## (调用预算|重试与限流|上下文压缩|防循环退出条件|输出要求)$' references/root_cause_enforcement.md; then
  echo "root_cause_enforcement.md should not define MCP control sections"
  exit 1
fi

if rg -q '^## (核心原则|排障标准流程|调用预算|重试与限流|防循环退出条件)$' references/examples.md; then
  echo "examples.md should not define root-cause or MCP control sections"
  exit 1
fi

echo "Layering guardrails OK"
echo "Base validation passed"
