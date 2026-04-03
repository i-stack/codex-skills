# 中英文术语表

## 目录
- 使用规则
- 总体命名规则
- 架构与分层术语
- 建模术语
- 并发术语
- UI 与状态术语
- 网络与数据术语
- 工程协作术语
- 禁止混用规则

## 使用规则
- 输出方案、代码审查、排障结论、架构设计、迁移计划时，必须使用本文件统一术语。
- 同一轮回答中，同一个概念只能使用一种主称呼。
- 需要保留英文术语时，首次出现使用“中文主称呼 + 英文原词”格式，后续固定使用同一称呼。

## 总体命名规则
- 面向中文叙述时，中文为主，英文为辅。
- 面向 Swift 类型、协议、枚举、文件名、模块名时，保留英文命名。
- Apple 官方框架、语言关键字、协议名、属性包装器保留英文原词。
- 禁止中英文来回切换导致一个概念出现多个别名。

## 架构与分层术语
| 统一称呼 | 英文原词 | 使用规则 |
|------|------|------|
| 架构边界 | Architecture Boundary | 叙述分层责任时使用 |
| 依赖注入 | Dependency Injection, DI | 首次可写“依赖注入（DI）” |
| 路由协调器 | Coordinator | 类型名保留 `Coordinator`，正文可写“路由协调器（Coordinator）” |
| 用例 | UseCase | 类型名保留 `UseCase` |
| 仓储 | Repository | 类型名保留 `Repository` |
| 服务 | Service | 类型名保留 `Service` |
| 功能模块 | Feature | 叙述业务模块时使用“功能模块”，代码名保留 `Feature` |
| 核心模块 | Core | 叙述基础层时使用“核心模块”，代码名保留 `Core` |

## 建模术语
| 统一称呼 | 英文原词 | 使用规则 |
|------|------|------|
| 传输模型 | DTO | 首次可写“传输模型（DTO）” |
| 领域实体 | Entity | 首次可写“领域实体（Entity）” |
| 页面状态 | ViewState | 首次可写“页面状态（ViewState）” |
| 错误模型 | ErrorModel | 首次可写“错误模型（ErrorModel）” |
| 映射层 | Mapper | 若明确存在独立层，可写“映射层（Mapper）” |

## 并发术语
| 统一称呼 | 英文原词 | 使用规则 |
|------|------|------|
| 主线程隔离 | @MainActor | 叙述规则时使用 |
| Actor 隔离 | actor | 保留关键字原词 |
| 结构化并发 | Structured Concurrency | 叙述并发模型时使用 |
| 取消语义 | Cancellation | 叙述任务取消规则时使用 |
| 可发送语义 | Sendable | 首次可写“可发送语义（Sendable）” |

## UI 与状态术语
| 统一称呼 | 英文原词 | 使用规则 |
|------|------|------|
| 页面状态机 | State Machine | 叙述复杂页面状态流时使用 |
| 空态 | Empty State | 叙述成功但无数据场景 |
| 错误态 | Error State | 叙述失败渲染场景 |
| 加载态 | Loading State | 叙述加载过程 |
| 列表身份 | Identity | 叙述列表稳定标识问题 |

## 网络与数据术语
| 统一称呼 | 英文原词 | 使用规则 |
|------|------|------|
| 请求端点 | Endpoint | 类型名保留 `Endpoint` |
| 请求构建器 | RequestBuilder | 类型名保留 `RequestBuilder` |
| API 客户端 | APIClient | 类型名保留 `APIClient` |
| 幂等 | Idempotency | 叙述写操作安全性时使用 |
| 游标分页 | Cursor-based Pagination | 叙述游标类分页 |
| 页码分页 | Page-based Pagination | 叙述页码类分页 |
| 鉴权刷新 | Token Refresh | 叙述 Token 更新链路 |

## 工程协作术语
| 统一称呼 | 英文原词 | 使用规则 |
|------|------|------|
| 代码审查 | Review | 正文统一写“代码审查”，必要时首次写“代码审查（Review）” |
| 合并请求 | PR | 正文统一写“PR” |
| 模块负责人 | Owner / Ownership | 正文统一写“模块负责人”或“ownership”之一；本 skill 统一写“模块 ownership” |
| 灰度发布 | Rollout | 叙述阶段放量时使用 |
| 回滚条件 | Rollback Condition | 叙述发布失败退出条件时使用 |

## 禁止混用规则
- 不要把 `DTO`、`Entity`、`ViewState`、`ErrorModel` 统称为 `Model`。
- 不要在同一段里混用“控制器”“VC”“ViewController”三种称呼。
- 不要在同一段里混用“代码审查”“Review”“PR Review”三种称呼。
- 不要在同一段里混用“所有权”“ownership”“owner 归属”三种称呼。
- 不要把“页面状态”“业务状态”“组件状态”混成一个“状态”。
