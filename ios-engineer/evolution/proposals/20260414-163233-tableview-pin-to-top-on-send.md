# Skill Evolution Proposal

## Metadata
- Proposal ID: 20260414-163233-tableview-pin-to-top-on-send
- Created At: 2026-04-14 16:32:33 +0800
- Active Version At Creation: v1

## 问题信号
- 真实任务（STOpenClawDetailView）中需要实现"用户发送消息后，新消息贴顶显示，bot 响应在其下方生长"的 UITableView 置顶功能。
- 现有 `layout_and_ui.md` 无任何 UITableView 滚动置顶的规则，导致首次实现时走了多个错误路径：
  1. 先用 `scrollToRow(at: .top)` → 流式响应每次 reloadData 覆盖置顶
  2. 再加 `isPinnedToTop` 布尔值拼状态 → 违反"不用多个布尔值拼状态"铁律
  3. 用 `cellForRow(at:)` 检查 cell 高度 → 新插入 cell 不可见时永远返回 nil，重试全失败
  4. 最终通过研读 `MainContentViewCollection.pinMessageToTop` 得出正确方案：`contentInset.bottom` 补偿 + `rectForRow` 检查 + `insertRows` 替代 `reloadData`

## 变更类型
- 新增能力：当前 skill 确实缺少 UITableView 聊天列表发送置顶的稳定规则。

## 变更内容
- 修改文件：`references/layout_and_ui.md`
  - 新增 "UITableView 发送消息置顶（Pin-to-top on send）" 章节
  - 扩展审查清单，增加两条置顶专项检查项
- 替代或合并旧规则：无对应旧规则，纯新增能力补丁。

## 预期收益
- 后续遇到聊天列表置顶需求时，直接命中正确机制（contentInset 补偿），不再经历多轮错误尝试。
- 避免"用多个 Bool 拼状态"反模式（如 `isPinnedToTop + isPinnedToBottom` 双布尔）在列表置顶场景重现。
- 减少 `cellForRow` vs `rectForRow` 的判断失误，直接说明两者的适用边界。

## 验证
- 结构校验：`layout_and_ui.md` 文件新增内容，不影响其他章节；原审查清单保留，追加 2 条专项项。
- 场景回放：STOpenClawDetailView 置顶完整实现已在真实任务中验证通过（insertRows + rectForRow + contentInset 补偿 + endLoading 清理）。
- 残留风险：仅覆盖 UITableView 场景；UICollectionView 的置顶机制（如 MainContentViewCollection 的 followUpPinStableId + autoFollow + scrollPolicy 方案）更复杂，暂不纳入本次提案。

## 状态
- validated
