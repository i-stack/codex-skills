# UI 布局与 HIG 规范 (Layout & Apple HIG)

追求极客级别的 UI 还原度体验，解决复杂页面的布局顽疾并且满足 Apple 原生标准。

## 1. AutoLayout 高级调试 (AutoLayout Debugger)
当处理 UIKit 视图不满足预期时：
- **冲突与歧义排查**：绝不靠暴力提高优先级（`Priority = 999`）掩人耳目。找出本质的多重约束 (`Ambiguous Layout`) 及发生冲突的确切层级结构并剥离多余元素。
- **抗伸与抗压机制**：熟练利用 `Content Hugging Priority`（防止组件随父视图拉伸变宽）与 `Content Compression Resistance Priority`（防止文字被邻居挤压变形），解决 StackView 横向比例乱窜等老残问题。
- **自适应内容**：依赖 `intrinsicContentSize` 让 View（例如动态尺寸 Cell、自适应高 Label）根据自身真实内容膨胀，杜绝硬编码固定高宽。

## 2. Apple HIG 审查 (Human Interface Guidelines)
合规与用户体验审核的必查硬性标准：
- **Dark Mode (深色模式)**：禁忌使用固定黑白字面值（如 `UIColor.black`），必须启用 Semantic Colors (系统语义化动态色) 和反转图像处理。
- **Dynamic Type (动态字体)**：不能强行锁死用户字体大小。排版必需支撑字号数倍放大下无字距重叠、控件破版，确保配合 `UIFontMetrics` 自适应。
- **Accessibility (无障碍化)**：视觉和操控入口配置 `accessibilityLabel` 和 `accessibilityTrait`，实现完美的 VoiceOver 支持。
