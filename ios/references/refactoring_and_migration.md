# 重构、迁移与代码审查 (Refactor, Migration & Review)

在维护巨石项目和遗留代码时，展示手术刀般精准的系统级架构翻新手段。

## 1. 大型文件重构 (Large File Refactor)
应对代码超标（动辄 2000 行以上）的 Mass-View-Controller 时：
- **结构拆解**：立即分而治之，抽取 `DataSource` 与 `Delegate` 文件，提取状态机至纯净的 ViewModel，按协议/关注点把功能分散为轻巧专精的 Service 层。
- **组件解耦**：彻底斩断业务与 UI 的死循环纠缠，实施工厂化（UI 组件工厂）、事件总线甚至 Router 控制抽离。

## 2. 并发世界改造 (Async/Await Migration)
将过时且容易出现死锁遗漏的逻辑全盘推向高安全世界：
- **消灭回调流**：运用 `withCheckedContinuation` / `withCheckedThrowingContinuation` 将以往带有大段 `completionHandler` 和 `GCD` 封印的老函数架接至结构化 `async/await`。
- **淘汰 GCD 排队陷阱**：利用 `Actor` 及 Task 执行流，剥离并替换以往用串行 DispatchQueue 和信号量构筑的老式锁层。

## 3. 生产级 Review (Code Review Checklist)
在做 Pull Request 审查或给出方案指导时，作为审查官实施铁面判罚：
- **架构越界**：警惕 Controller 里混进网络或解析代码，发现即退回。
- **并发盲区**：挑起状态无序读写或缺乏 `@MainActor` 并发域防护的数据污染案排查。
- **安全与内存漏点**：找出没有配搭 `[weak self]` 闭包及可能形成单例驻留内存死循环的结构。
