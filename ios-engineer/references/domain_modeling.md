# 领域建模

## 目录
- 使用规则
- 建模分层
- 实体建模规则
- DTO 建模规则
- ViewState 建模规则
- ErrorModel 建模规则
- 映射规则
- 常见反模式

## 使用规则
- 涉及实体设计、状态设计、错误设计、数据转换时，必须先定义建模分层。
- 不得把服务端返回结构直接当作领域模型或 UI 模型使用。
- 建模必须先回答三个问题：谁负责持有、谁负责转换、谁负责消费。

## 建模分层
固定分为四层：
- DTO：对应接口传输结构
- Entity：对应业务语义结构
- ViewState：对应界面渲染状态
- ErrorModel：对应业务或界面错误语义

要求：
- DTO 不得直接泄露到 ViewModel 和 View。
- Entity 不得携带 UIKit / SwiftUI 依赖。
- ViewState 不得反向污染 Repository 和 Service。
- ErrorModel 不得直接透传底层 `Error` 文本。

## 实体建模规则
- Entity 表达稳定业务语义，不表达接口噪音和 UI 临时状态。
- Entity 使用值语义，使用 `struct`。
- Entity 字段名使用业务语言，不复制后端命名噪音。
- Entity 必须可被测试和比较；需要时显式实现 `Equatable`。

适合放进 Entity 的内容：
- 用户、订单、商品、会话、权限、金额、时间区间

不适合放进 Entity 的内容：
- 占位文案
- Cell 展示文案
- 按钮是否禁用
- API 原始分页字段

## DTO 建模规则
- DTO 只负责解码和传输适配。
- DTO 可以保留接口字段命名，但必须在边界层完成转换。
- DTO 不承载业务方法，不参与 UI 判断。

适合放进 DTO 的内容：
- `page`
- `pageSize`
- `nextCursor`
- `rawStatus`
- `serverTimestamp`

## ViewState 建模规则
- ViewState 只表达界面渲染状态。
- ViewState 由 ViewModel 产出，不由 Repository 直接产出。
- ViewState 必须覆盖空态、加载态、错误态、成功态，不得只建成功态。

推荐形式：
- 枚举态：`idle / loading / loaded / failed`
- 组合态：列表内容、刷新状态、分页状态、提示状态

禁止：
- 把 ViewState 和 Entity 混成一个万能模型
- 用多个布尔值拼接复杂状态

## ErrorModel 建模规则
- 错误必须分层：网络错误、解码错误、鉴权错误、业务错误、展示错误。
- 面向 UI 的错误必须可映射为标题、文案、操作动作，而不是直接显示系统错误文本。
- ErrorModel 必须说明可恢复性和用户动作。

适合的设计方式：
- 领域层错误：表达业务失败语义
- 展示层错误：表达界面展示和交互动作

## 映射规则
- DTO -> Entity：发生在 Repository 或 Mapper 层
- Entity -> ViewState：发生在 ViewModel 层
- Error -> ErrorModel：发生在错误映射层或 ViewModel 边界

要求：
- 映射逻辑集中，不散落在 View、Cell、Service 多处。
- 一个方向只做一层转换，不混合多个语义层。

## 常见反模式
- 直接把 DTO 传给 View
- 把 Entity 直接改造成 CellModel 后又回传业务层
- 用一个 `Model` 同时承担 DTO、Entity、ViewState 三种职责
- 直接展示 `localizedDescription`
- 用多个布尔值组合复杂页面状态
