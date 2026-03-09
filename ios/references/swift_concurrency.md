# Swift 并发架构 (Swift Concurrency)

在处理任何异步、状态交互和线程分配时，必须以 Swift 6 严格并发检查（Strict Concurrency）标准执行代码。

## 1. 并发规则强制规范
- **禁止旧有模式**：不要轻易使用 `DispatchQueue.main.async` 或 `completion handlers`。全面迁移向 Structured Concurrency。
- **MainActor 护城河**：所有关于 UI 的更新、ViewModel 的状态变更发布，都必须用 `@MainActor` 标记和隔离。
- **生命周期**：异步操作应当挂靠明确层级的 `Task`（如 SwiftUI 的 `.task { }`），绝对不允许创建了就放任自流甚至导致内存泄漏的孤魂野鬼。

## 2. 检查重点与防范区
- **数据竞争 (Data Race) 与隔离**：凡是在并发域共享的可变状态，必须使用 `actor` 来防护，防止潜藏的多线程读取/赋值穿透。
- **跨界传递 (Sendable)**：从并发作用域传出传入的引用，强制符合 `Sendable` 协议。对于模型首推值语义的 `struct` 或 `enum`；难以更改的类对象必要时采用 `@unchecked Sendable` 配置专属锁管控。
- **结构化并发 (Structured Concurrency)**：需要并行时使用 `async let` / `TaskGroup` 将子任务建立出可传播取消层级树。禁止到处散落游离 `Task {}`。
