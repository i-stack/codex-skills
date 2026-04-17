# Validation Record

## Proposal ID
20260414-163233-tableview-pin-to-top-on-send

## Validation Date
2026-04-14

## Structural Checks
- SKILL.md frontmatter: OK
- layout_and_ui.md referenced file: exists
- Layering guardrails: no root_cause / output_template / tool_budget mixed into reference
- New section added to layout_and_ui.md without breaking existing sections: OK

## Scenario Replay
- Scenario: UITableView 聊天列表发送置顶（STOpenClawDetailView）
- Result: PASS
- Hit points:
  1. insertRows 替代 reloadData，避免全量刷新位移跳动
  2. rectForRow 替代 cellForRow，避免新 cell 不可见时重试全失败
  3. contentInset.bottom 补偿后 scrollToBottom = 用户消息贴顶，bot 响应向下生长
  4. endLoading 时 clearPinExtraInset + invalidatePinRetryToken 正确清理
  5. 不用 isPinnedToTop 布尔值拼状态，用 pinExtraBottomInset > 0 作为唯一信号
- Deviation points: none

## Status
validated
