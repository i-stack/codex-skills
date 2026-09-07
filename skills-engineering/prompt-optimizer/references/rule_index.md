<!-- last-verified: 2026-09 -->
# 规则 ID 索引（prompt-optimizer）

## 使用规则
- 本文件是 [SKILL.md](../SKILL.md) 内 `POPT-NNN` 规则的真值索引。新增 / 修改 / 退役 ID **先改本文，再同步 SKILL.md**。
- ID 格式：`^[A-Z]+-\d{3}$`，前缀 `POPT-` 专用于 prompt-optimizer（Prompt Optimizer）自有契约，不与 plan-grill 的 `PG-`、historical-recall 的 `HR-` 或全局 `GR-` 冲突。
- 编号可有空洞，无强制连续约束；新增条目用前缀内最大编号 +1。
- ID 一旦发布不复用：退役后保留在「退役记录」节，标 `retired` 并指明替代 ID；退役 ID 在 SKILL.md 中不应再出现。
- 行为门禁 `scripts/validate-skill-behavior.sh` 的 Check 2 会断言：SKILL.md 声明的每个 `POPT-NNN` 均在本文件以表格行 `| POPT-NNN |` 定义，且定义锚点须为标题 `## POPT-NNN` / 括号 `[POPT-NNN]` / 表格 `| POPT-NNN |` 之一；不一致即非零退出。

## Prompt Optimizer 规则 POPT-NNN

| ID | Status | 摘要 | SKILL.md 锚点 |
|----|--------|------|---------------|
| POPT-001 | active | 触发门控：仅主动触发（@prompt-optimizer 或「帮我优化提问/改写 prompt」类关键词），不做「发送时自动拦截」 | `## 六条核心规则` |
| POPT-002 | active | 历史召回：改写前针对原始提问 recall 相似历史，复用历史澄清结论、避免重复盘问 | 同上 |
| POPT-003 | active | 盘问判定与澄清：复用 plan-grill PG-000 门控，存在阻塞性歧义先逐一盘问澄清，无歧义直接改写 | 同上 |
| POPT-004 | active | 改写：宿主 AI 基于「盘问澄清 + 历史线索」把原始提问重写为结构化高质量提示词 | 同上 |
| POPT-005 | active | 透明确认与回答：先展示优化后提示词供用户确认/修正，确认后再基于它回答 | 同上 |
| POPT-006 | active | 回写闭环：归档 PROMPT-OPTIMIZATION.md 到 .plan-reviews 并 sync 回灌知识库 | 同上 |

## 退役记录

| ID | Status | 退役原因 | 替代 ID |
|----|--------|----------|---------|
| （暂无） | | | |
