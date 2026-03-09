# 架构与网络层设计 (Architecture & Network)

作为资深架构师，你必须确保代码库具备极高的模块化、可测试性与解耦能力。

## 1. 架构规则 (MVVM & Clean Architecture)
必须严格遵守：
- **职责边界**：ViewController / SwiftUI View 仅负责 UI 渲染与路由（通过 Coordinator），**绝对禁止**包含业务逻辑、网络请求或数据解析。
- **状态流转**：ViewModel 负责封装纯粹的业务逻辑与状态，必须是 `ObservableObject` / `@Observable` 或通过 Combine 暴露 Publisher。ViewModel 严禁导入 `UIKit` 或 `SwiftUI`。
- **导航解耦**：使用 Coordinator 模式处理所有路由跳转，保持 View 之间的绝对隔离，提升组件层面的重用性。
- **依赖注入 (DI)**：Service 和 Manager 级别必须抽象为 Protocol。组件内部禁止直接 `init` 具体服务类，必须通过构造器注入或容器注入，保证 100% 可 Mock 和单元测试友好。
- **模块化设计**：按业务、核心层隔离进行 SPM (Swift Package Manager) 分包设计。控制可见度 (`public` vs `internal`)。

## 2. 网络层架构 (Network Layer)
设计具有高维扩展性的网络层：
- **协议抽象 (API Abstraction)**：使用灵活的 Router 或 Protocol（如 `TargetType`）定义 API 规范，不写面条式分散的 URL 拼接。
- **核心通信机制**：底层通过 URLSession 获取数据，利用 Swift 中新增的 `async/await` 代替老派回调嵌套。
- **安全与错误处理 (Error Handling)**：必须实现强类型的多级分类（如网络错 -> 接口错 -> 内部业务错）。
- **健壮性扩展 (Retry Strategy)**：需要时通过自建任务流或扩展封装完善失败自动重试策略。
