# 极致性能优化 (UIKit & SwiftUI Performance)

优化是一场精确的数据指标驱动战役，无论是旧瓶装新酒的 UIKit 还是现代化的 SwiftUI。

## 1. SwiftUI 性能引擎
- **视图 Diff 剪枝**：SwiftUI 最害怕深层视图无脑全量刷新。核心策略是以细颗粒度拆散巨型视图，为底层属性添加 `Equatable`，使其不再被不相干的 `@State` 或者 Observable 模型大变动受牵连。
- **状态辐射范围**：管控状态 (`@State`, `@Binding`) 的辐射扇区，将逻辑剥离出根节点向下压低组件影响面。
- **结构渲染机制**：避免通过冗长的无限制 `List` 或嵌套导致过度生成；大数据量采用惰性初始化机制 `LazyVStack` 或按需组件映射重用。

## 2. UIKit 性能压榨
- **渲染管线与掉帧**：找出触发离屏渲染 (Offscreen Rendering) 的凶手，如非必要慎用带 CornerRadius 及 MaskToBounds 的阴影并举（使用预设纯色遮罩曲线或直接渲染背景缓存代替）。
- **层级复杂度与重用**：将极度复杂的列表推离 AutoLayout 同步算距的魔爪。将高度计算后置于背景并发中运算、剥离数据组装逻辑；强化 Table/Collection 的 Cell 同等模型复用率缓冲（避免频繁初始化复杂组合对象）。
- **工具剖析**：借助 `Time Profiler` 扫荡主线程耗时占比；巧用 Core Animation Instruments 查看混合、帧频。
