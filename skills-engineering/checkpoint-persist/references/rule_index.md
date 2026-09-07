<!-- last-verified: 2026-09 -->
# 规则 ID 索引（checkpoint-persist）

## 使用规则
- 本文件是 [SKILL.md](../SKILL.md) 内 `CP-NNN` 规则的真值索引。新增 / 修改 / 退役 ID **先改本文，再同步 SKILL.md**。
- ID 格式：`^[A-Z]+-\d{3}$`，前缀 `CP-` 专用于 checkpoint-persist（Checkpoint Persist）自有契约，不与 ios-engineer 的 `IR-/SYM-/ROUTE-/OUT-`、全局 `GR-` 或 historical-recall 的 `HR-` 冲突。
- 编号可有空洞，无强制连续约束；新增条目用前缀内最大编号 +1。
- ID 一旦发布不复用：退役后保留在「退役记录」节，标 `retired` 并指明替代 ID；退役 ID 在 SKILL.md 中不应再出现。
- 行为门禁 `scripts/validate-skill-behavior.sh` 的 Check 2 会断言：SKILL.md 声明的每个 `CP-NNN` 均在本文件以表格行 `| CP-NNN |` 定义，且定义锚点须为标题 `## CP-NNN` / 括号 `[CP-NNN]` / 表格 `| CP-NNN |` 之一；不一致即非零退出。

## Checkpoint Persist 规则 CP-NNN

| ID | Status | 摘要 | SKILL.md 锚点 |
|----|--------|------|---------------|
| CP-001 | active | 触发门控：非平凡任务 + ≥2 子结论 + 跨轮存活三条全满足才落盘；trivial / 单轮可完成 / 单点子结论 / 闲聊跳过 | `## 规则索引` |
| CP-002 | active | 落盘对象与粒度：只落「结论 + 关键决策 + 未决问题」，不落对话过程与思考流；最小单元 = 单个子结论，且须自包含 | 同上 |
| CP-003 | active | 落盘时机：每产出一个子结论立即追加，禁止攒批；感知上下文将超窗 / 压缩时优先补齐落盘 | 同上 |
| CP-004 | active | 落盘位置与格式：固定写 `<工作区根>/.plan-reviews/checkpoint/<task-slug>/CHECKPOINT.md`，统一模板，压缩后可按约定路径找回 | 同上 |
| CP-005 | active | 恢复与生命周期：新轮次先读进行中 checkpoint 恢复；任务完成（结论入成品产出）后清理；落盘失败 best-effort 不阻断，须并入 GR-008 残留风险 | 同上 |

## 退役记录

| ID | Status | 退役原因 | 替代 ID |
|----|--------|----------|---------|
| （暂无） | | | |
