#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/create_skill_proposal.sh <proposal-slug>"
  exit 1
fi

slug="$1"
timestamp="$(date '+%Y%m%d-%H%M%S')"
proposal_path="evolution/proposals/${timestamp}-${slug}.md"

cat > "$proposal_path" <<EOF
# Skill Evolution Proposal

## Metadata
- Proposal ID: ${timestamp}-${slug}
- Created At: $(date '+%Y-%m-%d %H:%M:%S %z')
- Active Version At Creation: $(ruby -rjson -e 'print JSON.parse(File.read("evolution/active_version.json"))["active_version"]')

## 问题信号
- 

## 变更类型
- 新增能力 / 修正表达 / 合并重复 / 退役规则

## 变更内容
- 修改文件：
- 替代或合并旧规则：

## 预期收益
- 

## 验证
- 结构校验：
- 场景回放：
- 残留风险：

## 状态
- draft
EOF

echo "$proposal_path"
