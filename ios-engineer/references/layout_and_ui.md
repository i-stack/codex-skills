# UI 布局与 HIG 规范

## 适用场景
用于以下问题：
- Auto Layout 冲突、页面错位、列表高度异常
- SwiftUI 视图抖动、跳动、刷新过多、导航状态错乱
- Dark Mode、Dynamic Type、无障碍支持缺失
- 高保真还原、复杂表单、复杂列表和混合布局

## UIKit 布局诊断顺序
排查顺序固定为：
1. 视图层级是否合理
2. 约束数量是否完整且无冲突
3. `contentHugging` / `compressionResistance` 是否正确
4. 是否错误依赖固定宽高
5. 是否被复用、异步回填或隐藏逻辑影响

要求：
- 布局排查按以上顺序收敛，不并行罗列多个大候选方向。
- 输出时优先指出当前最可能断链点，再补充次要可能性。

### UIKit 约束规则
- 非必要场景不得使用 `999` 这类“接近必选”的优先级掩盖设计问题；只有在明确说明约束意图且常规约束方案不成立时才允许使用。
- 约束先表达相对关系和内容驱动链路，不先依赖写死宽高、魔法间距或补丁式尺寸。
- 出现约束冲突时，先修正视图层级和约束设计，不先通过调优优先级规避问题。
- 通过完整约束关系表达布局，不靠 `layoutIfNeeded()` 硬催。
- 复杂 Cell 要明确内容边界、间距来源和自适应高度链路。
- 自适应高度必须能解释清楚由谁撑开、约束如何闭合、何处可能因隐藏或复用断链。
- 不在 `layoutSubviews`、`updateConstraints` 或同类高频生命周期里反复创建、激活或重建约束。
- 使用 Auto Layout 时，必须明确 `translatesAutoresizingMaskIntoConstraints` 的开启或关闭语义，避免系统约束和手写约束混杂失控。
- `UIStackView` 适合线性布局，不适合承载复杂、条件分支很多的页面骨架。

### 自适应内容
- 依赖 `intrinsicContentSize` 和约束链路实现自适应。
- 文本、多语言、超长文案、极端字号必须纳入验证范围。
- 列表高度计算要考虑异步图片、富文本、展开收起和复用回写。

## SwiftUI 视图设计规则
### 状态管理
- 将状态粒度压低，避免根 View 持有过大的可变状态。
- 不把网络请求、埋点、导航副作用直接写在 `body` 的临时闭包里。
- 必须保证 `id` 稳定，避免列表闪烁、滚动位置丢失、视图状态错位。

### 布局稳定性
- 必须理解 `frame`、`fixedSize`、`layoutPriority`、`alignment` 的语义，禁止层层叠 modifier 试错。
- 避免不必要的 `GeometryReader` 扩散。
- 针对复杂滚动页，评估 `LazyVStack`、分段加载和子视图拆分。

## 列表与复用
- UIKit 列表关注复用标识、异步任务取消、图片回填错位、状态残留。
- SwiftUI 列表关注身份稳定、最小刷新范围和数据源 diff 质量。
- 任何列表问题都要同时检查“数据源、复用链路、异步回填、布局约束”四条线。

## 自动布局补充检查
- 多行文本、自适应高度、长文案、多语言和极端字号视为默认验证项，不是额外加测项。
- 隐藏、折叠、展开、占位切换和异步内容回填后，必须重新检查约束链路是否仍然闭合。
- 对嵌套滚动、复杂表单、动态列表页，先判断是否是层级设计问题，再判断是否是单条约束问题。
- SwiftUI 出现跳动、闪烁、错位时，同时检查 `id` 稳定性、状态粒度和刷新边界，不把所有现象都归因于布局。

## Apple HIG 与可访问性
### 基本要求
- 使用语义色、动态字体和系统交互反馈。
- 交互区域、层级层次、返回路径和空状态要符合 iOS 用户习惯。
- 不为了“像设计稿”而破坏平台交互一致性。

### 无障碍要求
- 关键控件提供准确的 `accessibilityLabel`、`accessibilityHint`、`accessibilityTraits`。
- 焦点顺序、朗读内容和可点击区域必须可用。
- 图片和图标要区分装饰性资源与有语义资源。

## 常见反模式
- 通过写死宽高、额外加空白 View、疯狂调优先级解决布局问题。
- 在 Cell/Item 复用场景里忘记重置状态和取消异步任务。
- 在 `layoutSubviews` 或约束更新回调中不断重建约束，导致抖动、冲突或性能退化。
- 把 Auto Layout 问题简化成“多调几个优先级总能过”。
- SwiftUI 中把多个业务状态塞进一个大对象，导致整页刷新。
- 为赶进度忽略 Dark Mode、Dynamic Type、VoiceOver。

## UITableView 发送消息置顶（Pin-to-top on send）

### 适用场景
聊天列表中用户发送消息后，需要将该用户消息显示在屏幕顶部，同时 bot 响应在其下方向下生长。

### 核心机制：contentInset.bottom 补偿（参考 MainContentViewCollection.pinMessageToTop）
**禁止**用 `scrollToRow(at:, at: .top)` 强制置顶——它无法与流式响应的 `scrollToBottom` 兼容。
**正确方案**：补偿 `contentInset.bottom`，使 `scrollToBottom` 后用户消息恰好落在视口顶部。

```swift
// 1. 发送时仅插入最后一行（不走 reloadData，避免全量刷新位移跳动）
UIView.performWithoutAnimation {
    self.tableView.insertRows(at: [lastIndexPath], with: .none)
}
// 2. 强制完成布局，确保 rectForRow 有效
self.tableView.layoutIfNeeded()
// 3. 取用户消息的 rect，计算从其顶部到内容末尾的高度
let userRect = self.tableView.rectForRow(at: userIndexPath)
let heightFromUserToEnd = self.tableView.contentSize.height - userRect.minY
let viewportHeight = self.tableView.bounds.height
    - self.tableView.adjustedContentInset.top
    - self.tableView.adjustedContentInset.bottom
// 4. 补偿 bottom inset，让 scrollToBottom 后用户消息恰好贴顶
let needed = max(0, viewportHeight - heightFromUserToEnd)
if needed > 0.5 {
    self.tableView.contentInset.bottom += needed
}
// 5. 执行 scrollToBottom（isPinnedToBottom = true 保证流式响应继续自动跟随）
self.scrollToLatest(animated: false)
```

### 状态机设计
- `isPinnedToBottom: Bool`：是否处于"底部跟随"模式（发送后置为 true，让流式响应继续自动下滚）。
- `pendingForceScroll: Bool`：发送时设为 true，下次 reloadData 触发置顶插入逻辑。
- `pinExtraBottomInset: CGFloat`：记录本次补偿量，响应结束或手动滚底时用 `clearPinExtraInset()` 还原。
- `pinRetryToken: UUID`：置顶重试链的失效令牌，响应结束时更新，旧重试任务自动失效。

**禁止**用多个 Bool 拼状态（如同时维护 `isPinnedToTop` + `isPinnedToBottom`），应收敛到 `pinExtraBottomInset > 0` 作为"置顶激活"的唯一信号。

### 重试机制（等待 cell 布局就绪）
`rectForRow` 返回零高说明 cell 尚未完成布局，需重试：

```swift
private func pinLastUserMessageToTop(retryToken: UUID, remainingAttempts: Int = 3) {
    guard retryToken == self.pinRetryToken else { return }
    // ...取 userRect...
    guard userRect.height > 0.5 else {
        guard remainingAttempts > 1 else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.02) { [weak self] in
            self?.pinLastUserMessageToTop(retryToken: retryToken, remainingAttempts: remainingAttempts - 1)
        }
        return
    }
    // ...执行补偿和滚动...
}
```

### 生命周期清理
| 时机 | 操作 |
|---|---|
| 响应结束（`endLoading`）| `clearPinExtraInset()` + `invalidatePinRetryToken()` |
| 用户手动点"↓"滚到底 | `clearPinExtraInset()` + `invalidatePinRetryToken()` + `scrollToLatest()` |
| 用户手动滑到底部（`scrollViewDidScroll`）| 无需额外操作，`isPinnedToBottom = true` 自然接管流式跟随 |

### 常见陷阱
- **不能用 `scrollToRow(at: .top)`**：发送后流式响应的每次 `reloadData` 都会 `scrollToBottom`，覆盖置顶。
- **`cellForRow(at:)` 检查 cell 高度不可靠**：新插入 cell 未进入可视区时永远返回 nil，导致重试全部失败。正确做法是用 `rectForRow`（即使 cell 不可见也能返回布局数据）。
- **`reloadData` 会触发 `contentOffset` 重置**：用户消息插入时必须用 `insertRows`，否则已有内容的视觉位置会跳动。
- **补偿 inset 必须在响应结束后还原**：不还原会导致列表底部出现永久空白。

## 审查清单
- [ ] 布局是否由明确约束或明确的 SwiftUI 布局语义驱动？
- [ ] 是否兼容长文本、多语言、极端字号和深色模式？
- [ ] 列表或表单是否考虑了复用、回填、焦点和滚动稳定性？
- [ ] 是否存在身份不稳定、过度刷新或错误的状态归属？
- [ ] 是否补齐了无障碍和平台一致性要求？
- [ ] 聊天列表置顶：是否用 contentInset.bottom 补偿而非 scrollToRow(.top)？
- [ ] 聊天列表置顶：响应结束后是否清除了补偿 inset 和重试 token？
